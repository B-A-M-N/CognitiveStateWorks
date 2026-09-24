#!/usr/bin/env python3
"""Validated packet and transition primitives for CognitiveStateWork."""
from __future__ import annotations

import json
import copy
import fcntl
import hashlib
import os
import tempfile
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional
from datetime import datetime, timezone

import jsonschema
import yaml
from importlib.resources import files as resource_files

ROOT = (Path(__file__).resolve().parent
        if (Path(__file__).resolve().parent / "schemas").is_dir()
        else Path(__file__).resolve().parents[1])
EVIDENCE_KIND_REGISTRY_PATH = ROOT / "schemas" / "evidence-kinds.yaml"


class PacketValidationError(ValueError):
    pass


class TransitionError(ValueError):
    pass


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _package_resource(relative: str):
    try:
        resource = resource_files("cognitive_statework").joinpath(relative)
        if resource.is_file():
            return resource
    except (ModuleNotFoundError, FileNotFoundError):
        pass
    return None


def _schema_resource(name: str):
    return _package_resource(f"schemas/{name}")


def _schema_text(name: str) -> str:
    resource = _schema_resource(name)
    if resource is not None:
        return resource.read_text(encoding="utf-8")
    return (ROOT / "schemas" / name).read_text(encoding="utf-8")


def load_evidence_kind_registry(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and validate the semantic evidence provenance registry."""
    if path is None and _package_resource("schemas/evidence-kinds.yaml") is not None:
        resource = _package_resource("schemas/evidence-kinds.yaml")
        data = yaml.safe_load(resource.read_text(encoding="utf-8"))
        schema = json.loads(_schema_text("evidence-kinds.schema.json"))
        jsonschema.validate(instance=data, schema=schema)
        return data
    registry_path = Path(path or EVIDENCE_KIND_REGISTRY_PATH)
    data = _load_yaml(registry_path)
    schema_path = registry_path.with_suffix(".schema.json")
    if schema_path.exists():
        jsonschema.validate(instance=data, schema=json.loads(schema_path.read_text(encoding="utf-8")))
    return data


def _local_schema_registry() -> "jsonschema.validators.Registry":
    from referencing import Registry, Resource
    registry = Registry()
    resources = []
    try:
        resources = sorted(resource_files("cognitive_statework").joinpath("schemas").iterdir(),
                           key=lambda item: item.name)
    except (ModuleNotFoundError, FileNotFoundError):
        resources = sorted((ROOT / "schemas").glob("*.json"))
    for path in resources:
        if not path.name.endswith(".json"):
            continue
        schema = json.loads(path.read_text(encoding="utf-8"))
        uri = schema.get("$id")
        if uri:
            registry = registry.with_resource(uri, Resource.from_contents(schema))
    return registry


def _repository_truth_v1(packet: Dict[str, Any], context: Mapping[str, Any]) -> bool:
    """Trusted repository-currentness validator selected by the registry."""
    repo_path = context.get("repository_path")
    if repo_path:
        import importlib.util
        module_path = ROOT / "validate-repository-truth.py"
        if not module_path.exists():
            module_path = ROOT / "scripts" / "validate-repository-truth.py"
        spec = importlib.util.spec_from_file_location(
            "cognitive_statework_repository_truth", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return bool(module.validate_repository_truth_packet(
            packet, Path(repo_path)).get("valid"))
    expected_vector = context.get("repository_freshness")
    actual_vector = packet.get("payload", {}).get("freshness", {})
    required = ("repo_identity", "observed_head", "working_tree_fingerprint",
                "active_worktree_snapshot", "remote_state_fingerprint")
    if not isinstance(expected_vector, Mapping):
        return False
    return all(key in expected_vector and expected_vector.get(key) == actual_vector.get(key)
               for key in required)


def _infrastructure_truth_v1(packet: Dict[str, Any], context: Mapping[str, Any]) -> bool:
    expected = context.get("infrastructure_fingerprint")
    actual = packet.get("payload", {}).get("freshness_fingerprint")
    return bool(expected and actual == expected)


def _tui_validation_v1(packet: Dict[str, Any], context: Mapping[str, Any]) -> bool:
    expected = context.get("validation_fingerprint")
    actual = packet.get("payload", {}).get("freshness_fingerprint")
    return bool(expected and actual == expected)


# Packet types select validators by immutable registry ID.  Callers may supply
# observations, but never replace this dispatch table with a callable.
FRESHNESS_VALIDATORS = {
    "repository_truth_v1": _repository_truth_v1,
    "infrastructure_truth_v1": _infrastructure_truth_v1,
    "tui_validation_v1": _tui_validation_v1,
}


class EvidenceStore:
    """Trusted evidence authority with immutable revisions and locked merge."""
    def __init__(self, records: Optional[Iterable[Mapping[str, Any]]] = ()) -> None:
        self._records: Dict[str, Dict[str, Any]] = {}
        for record in records or ():
            self.put(record)

    @staticmethod
    def _digest(record: Mapping[str, Any]) -> str:
        body = dict(record)
        body.pop("attestation_digest", None)
        body.pop("revisions", None)
        body.pop("invalidation_events", None)
        body["invalidated"] = body.get("invalidated") is True
        return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

    def _current_body(self, record: Mapping[str, Any]) -> Dict[str, Any]:
        return {key: value for key, value in dict(record).items() if key not in {"revisions", "invalidation_events"}}

    def put(self, record: Mapping[str, Any]) -> str:
        if not isinstance(record, Mapping):
            raise TransitionError("trusted evidence record must be a mapping")
        ref = record.get("ref")
        kind = record.get("kind")
        if not isinstance(ref, str) or not ref or not isinstance(kind, str) or not kind:
            raise TransitionError("trusted evidence requires ref and kind")
        candidate = self._current_body(record)
        candidate["invalidated"] = candidate.get("invalidated") is True
        digest = self._digest(candidate)
        candidate["attestation_digest"] = digest
        prior = self._records.get(ref)
        if prior is not None and self._digest(self._current_body(prior)) != digest:
            raise TransitionError(f"evidence reference {ref!r} has conflicting trusted content")
        if prior is None:
            candidate["revisions"] = list(record.get("revisions") or [dict(candidate)])
            candidate["invalidation_events"] = list(record.get("invalidation_events") or [])
        else:
            candidate["revisions"] = list(prior.get("revisions") or [self._current_body(prior)])
            candidate["invalidation_events"] = list(prior.get("invalidation_events") or [])
        self._records[ref] = candidate
        return ref

    def resolve(self, refs: Iterable[str]) -> List[Dict[str, Any]]:
        out = []
        for ref in refs:
            record = self._records.get(str(ref))
            if record is None:
                raise TransitionError(f"evidence reference {ref!r} is not present in the trusted store")
            current = self._current_body(record)
            if self._digest(current) != record.get("attestation_digest"):
                raise TransitionError(f"evidence reference {ref!r} has an invalid attestation digest")
            out.append(dict(current))
        return out

    def invalidate(self, ref: str) -> None:
        if ref not in self._records:
            raise TransitionError(f"cannot invalidate unknown evidence reference {ref!r}")
        record = self._records[ref]
        if record.get("invalidated") is True:
            return
        original = self._current_body(record)
        record["revisions"] = list(record.get("revisions") or []) + [dict(original)]
        record["invalidation_events"] = list(record.get("invalidation_events") or []) + [{
            "event": "invalidated", "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "previous_revision_digest": original.get("attestation_digest"),
        }]
        record["invalidated"] = True
        record["attestation_digest"] = self._digest(record)

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        lock_path = path.with_name(path.name + ".lock")
        with lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            persisted = EvidenceStore()
            if path.exists():
                try:
                    for record in json.loads(path.read_text(encoding="utf-8")):
                        persisted.put(record)
                except (OSError, json.JSONDecodeError, TransitionError) as exc:
                    raise TransitionError("trusted evidence store is unreadable") from exc
            for ref, record in self._records.items():
                if ref not in persisted._records:
                    persisted._records[ref] = dict(record)
                else:
                    left = persisted._records[ref]
                    left_body = self._current_body(left)
                    right_body = self._current_body(record)
                    left_base = dict(left_body); right_base = dict(right_body)
                    left_base["invalidated"] = False; right_base["invalidated"] = False
                    if self._digest(left_base) == self._digest(right_base):
                        left["invalidated"] = bool(left.get("invalidated") or record.get("invalidated"))
                        left["invalidation_events"] = list(left.get("invalidation_events") or []) + list(record.get("invalidation_events") or [])
                        left["revisions"] = list(left.get("revisions") or []) + list(record.get("revisions") or [])[-(len(record.get("revisions") or []) - len(left.get("revisions") or [])):]
                        left["attestation_digest"] = self._digest(left)
                    else:
                        raise TransitionError(f"evidence reference {ref!r} conflicts during merge")
            fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(list(persisted._records.values()), stream, sort_keys=True, separators=(",", ":"))
                    stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
                os.chmod(temporary, 0o600); os.replace(temporary, path)
            finally:
                if os.path.exists(temporary): os.unlink(temporary)


class SubjectStateStore:
    """Durable authoritative current state plus append-only history.

    Identity is namespace/application/subject/statework/contract-version. Writers
    use compare-and-swap revisions; stale writers must re-inspect rather than
    overwrite a newer state.
    """
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._data = {"version": 1, "revision": 0, "subjects": {}, "history": []}
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TransitionError("subject state store is unreadable") from exc
        if not isinstance(data, dict) or not isinstance(data.get("subjects"), dict):
            raise TransitionError("subject state store has invalid structure")
        self._data = data

    def _save(self) -> None:
        fd, temporary = tempfile.mkstemp(dir=str(self.path.parent), prefix=f".{self.path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self._data, stream, sort_keys=True, separators=(",", ":"))
                stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
            os.chmod(temporary, 0o600); os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    @staticmethod
    def key(identity: Mapping[str, Any]) -> str:
        fields = [identity.get(name) for name in ("namespace_id", "application_id", "subject_ref", "statework_id", "contract_version")]
        if any(not isinstance(value, str) or not value for value in fields):
            raise TransitionError("subject state identity requires namespace, application, subject, StateWork, and contract version")
        return json.dumps(dict(zip(("namespace_id", "application_id", "subject_ref", "statework_id", "contract_version"), fields)), sort_keys=True, separators=(",", ":"))

    def _refresh(self) -> None:
        if self.path.exists():
            self._load()

    def get(self, identity: Mapping[str, Any]) -> Dict[str, Any]:
        self._refresh()
        return dict(self._data["subjects"].get(self.key(identity)) or {"state": None, "revision": 0})

    def commit(self, identity: Mapping[str, Any], *, expected_revision: int, new_state: str, transition: Mapping[str, Any]) -> Dict[str, Any]:
        key = self.key(identity)
        self.lock_path.touch(mode=0o600, exist_ok=True)
        with self.lock_path.open("r+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            self._refresh()
            current = self._data["subjects"].get(key) or {"state": None, "revision": 0}
            if int(current.get("revision", 0)) != int(expected_revision):
                raise TransitionError(f"subject state revision conflict: expected {expected_revision}, found {current.get('revision', 0)}; re-inspect required")
            revision = int(expected_revision) + 1
            record = dict(identity); record.update({"state": new_state, "revision": revision, "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})
            self._data["subjects"][key] = record
            self._data["history"].append({"identity": dict(identity), "from_state": current.get("state"), "to_state": new_state, "revision": revision, "transition": dict(transition)})
            self._save()
            return record


class PacketStore:
    """Validated typed handoff packets. Presence alone is never truth."""

    def __init__(self, packets: Optional[Iterable[Dict[str, Any]]] = None,
                 packet_registry_path: Optional[Path] = None,
                 storage_path: Optional[Path] = None,
                 secure_storage_dir: bool = False) -> None:
        registry_path = packet_registry_path
        if registry_path is None:
            registry_resource = _package_resource("schemas/packet-registry.yaml")
            data = yaml.safe_load(registry_resource.read_text(encoding="utf-8")) if registry_resource else _load_yaml(ROOT / "schemas" / "packet-registry.yaml")
            registry_schema_text = _schema_text("packet-registry.schema.json")
        else:
            data = _load_yaml(registry_path)
            registry_schema = registry_path.with_name("packet-registry.schema.json")
            registry_schema_text = registry_schema.read_text(encoding="utf-8") if registry_schema.exists() else None
        if registry_schema_text:
            jsonschema.validate(
                instance=data, schema=json.loads(registry_schema_text))
        self.registry: Dict[str, Dict[str, Any]] = data.get("packets", {})
        self._packets: Dict[str, Dict[str, Any]] = {}
        self._digests: Dict[str, str] = {}
        self.revision = 0
        self.storage_path = Path(storage_path) if storage_path else None
        self.secure_storage_dir = bool(secure_storage_dir)
        if self.storage_path is not None and self.storage_path.exists():
            try:
                stored = json.loads(self.storage_path.read_text(encoding="utf-8"))
                self.revision = int(stored.get("revision", 0) or 0)
                stored_packets = stored.get("packets", [])
                if isinstance(stored_packets, dict):
                    stored_packets = list(stored_packets.values())
                for packet in stored_packets:
                    self.put(packet, persist=False)
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
                raise PacketValidationError(
                    f"persistent packet authority is unreadable: {self.storage_path}") from exc
        for packet in packets or []:
            self.put(packet)

    def _validate(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        packet_type = packet.get("packet_type")
        meta = self.registry.get(packet_type)
        if not meta:
            raise PacketValidationError(f"unknown packet type {packet_type!r}")
        if packet.get("producer") != meta.get("producer"):
            raise PacketValidationError(
                f"packet {packet_type!r} producer {packet.get('producer')!r} "
                f"is not registered producer {meta.get('producer')!r}")
        if packet.get("schema_version") != str(meta.get("schema_version")):
            raise PacketValidationError(
                f"packet {packet_type!r} schema version mismatch")
        schema = json.loads(_schema_text(str(meta.get("schema"))))
        validator = jsonschema.Draft202012Validator(
            schema, registry=_local_schema_registry(),
            format_checker=jsonschema.FormatChecker())
        errors = sorted(validator.iter_errors(packet), key=lambda e: list(e.path))
        if errors:
            raise PacketValidationError(errors[0].message)
        from datetime import datetime
        try:
            datetime.fromisoformat(packet["observed_at"].replace("Z", "+00:00"))
        except Exception as exc:
            raise PacketValidationError(f"invalid observed_at: {exc}") from exc
        return packet

    def _persist(self, packets: Mapping[str, Dict[str, Any]],
                 digests: Mapping[str, str], expected_revision: int) -> int:
        if self.storage_path is None:
            return expected_revision
        self.storage_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.secure_storage_dir:
            os.chmod(self.storage_path.parent, 0o700)
        lock_path = self.storage_path.with_name(self.storage_path.name + ".lock")
        with lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                current_revision = 0
                if self.storage_path.exists():
                    try:
                        current = json.loads(self.storage_path.read_text(encoding="utf-8"))
                        current_revision = int(current.get("revision", 0) or 0)
                    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
                        raise PacketValidationError(
                            f"persistent packet authority is unreadable: {self.storage_path}") from exc
                if current_revision != expected_revision:
                    raise PacketValidationError(
                        f"packet store revision conflict: expected {expected_revision}, "
                        f"found {current_revision}; reload before writing")
                fd, temporary = tempfile.mkstemp(dir=str(self.storage_path.parent),
                                                 prefix=f".{self.storage_path.name}.", suffix=".tmp")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as stream:
                        json.dump({"revision": expected_revision + 1,
                                   "packets": [packets[key] for key in sorted(packets)],
                                   "digests": {key: digests[key] for key in sorted(digests)}},
                                  stream, sort_keys=True, separators=(",", ":"))
                        stream.write("\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.chmod(temporary, 0o600)
                    os.replace(temporary, self.storage_path)
                    directory_fd = os.open(self.storage_path.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        os.chmod(self.storage_path, 0o600)
        os.chmod(lock_path, 0o600)
        return expected_revision + 1

    def put(self, packet: Dict[str, Any], *, persist: bool = True) -> str:
        candidate = copy.deepcopy(packet)
        self._validate(candidate)
        packet_id = candidate["packet_id"]
        digest = hashlib.sha256(json.dumps(
            candidate, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")).hexdigest()
        if packet_id in self._packets and self._digests[packet_id] != digest:
            raise PacketValidationError(f"conflicting packet id {packet_id!r}")
        candidate_packets = copy.deepcopy(self._packets)
        candidate_digests = dict(self._digests)
        candidate_packets[packet_id] = candidate
        candidate_digests[packet_id] = digest
        if persist:
            new_revision = self._persist(candidate_packets, candidate_digests, self.revision)
            self._packets = candidate_packets
            self._digests = candidate_digests
            self.revision = new_revision
        else:
            self._packets = candidate_packets
            self._digests = candidate_digests
        return packet_id

    def reload(self) -> None:
        """Replace live state from durable storage after a conflict."""
        if self.storage_path is None or not self.storage_path.exists():
            raise PacketValidationError("packet store has no durable state to reload")
        stored = json.loads(self.storage_path.read_text(encoding="utf-8"))
        revision = int(stored.get("revision", 0) or 0)
        packets = stored.get("packets", [])
        if isinstance(packets, dict):
            packets = list(packets.values())
        loaded_packets: Dict[str, Dict[str, Any]] = {}
        loaded_digests: Dict[str, str] = {}
        for packet in packets:
            candidate = copy.deepcopy(packet)
            self._validate(candidate)
            packet_id = candidate["packet_id"]
            digest = hashlib.sha256(json.dumps(
                candidate, sort_keys=True, separators=(",", ":"), default=str
            ).encode("utf-8")).hexdigest()
            loaded_packets[packet_id] = candidate
            loaded_digests[packet_id] = digest
        self._packets, self._digests, self.revision = loaded_packets, loaded_digests, revision

    def get(self, packet_id: str) -> Optional[Dict[str, Any]]:
        """Read a previously validated typed packet by immutable identity."""
        packet = self._packets.get(packet_id)
        return copy.deepcopy(packet) if packet is not None else None

    def packet_digest(self, packet_id: str) -> Optional[str]:
        return self._digests.get(packet_id)

    def get_schema_valid(self, packet_type: str, *, task_id: str,
                         subject_ref: str) -> Optional[Dict[str, Any]]:
        """Return the newest schema-valid, task/subject-bound packet.

        This deliberately does not claim that external reality is current.
        Callers that use a truth packet to authorize a transition must use
        :meth:`get_current` with an observation context.
        """
        matches = [
            p for p in self._packets.values()
            if p.get("packet_type") == packet_type and p.get("task_id") == task_id
            and p.get("subject_ref") == subject_ref and not p.get("invalidated_by")
        ]
        if not matches:
            return None
        return copy.deepcopy(sorted(matches, key=lambda p: datetime.fromisoformat(
            p["observed_at"].replace("Z", "+00:00")), reverse=True)[0])

    def validate_current(self, packet: Dict[str, Any], *, observation_context: Optional[Mapping[str, Any]] = None) -> bool:
        """Run the packet-type freshness validator against current reality."""
        context = dict(observation_context or {})
        meta = self.registry.get(packet.get("packet_type"), {})
        validator_id = meta.get("freshness_validator")
        if meta.get("freshness") == "immutable":
            return True
        validator = FRESHNESS_VALIDATORS.get(validator_id)
        if validator is None:
            return False
        required_context = list(meta.get("required_context") or [])
        required_any_context = list(meta.get("required_any_context") or [])
        if required_context and not all(context.get(key) for key in required_context):
            return False
        if required_any_context and not any(context.get(key) for key in required_any_context):
            return False
        return bool(validator(packet, context))

    def get_current(self, packet_type: str, *, task_id: str, subject_ref: str,
                    observation_context: Optional[Mapping[str, Any]] = None) -> Optional[Dict[str, Any]]:
        matches = [
            copy.deepcopy(packet) for packet in self._packets.values()
            if packet.get("packet_type") == packet_type
            and packet.get("task_id") == task_id
            and packet.get("subject_ref") == subject_ref
            and not packet.get("invalidated_by")
        ]
        valid = [packet for packet in matches
                 if self.validate_current(packet, observation_context=observation_context)]
        if not valid:
            return None
        return sorted(valid, key=lambda p: datetime.fromisoformat(
            p["observed_at"].replace("Z", "+00:00")), reverse=True)[0]

    def fresh_repository_truth(self, *, task_id: str, expected_subject_ref: str,
                               repository_freshness: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        """Return repository truth only when every freshness dimension matches."""
        observation_context = {"repository_freshness": dict(repository_freshness)}
        packet = self.get_current(
            "repository_truth_packet", task_id=task_id,
            subject_ref=expected_subject_ref, observation_context=observation_context)
        if packet is None:
            return None
        freshness = packet.get("payload", {}).get("freshness", {})
        if dict(freshness) != dict(repository_freshness):
            return None
        return packet


class StandaloneStateWorkController:
    """Enforcing CSW-only host controller for one durable subject identity.

    The controller, not the caller, owns the current state. Every request
    atomically checks the expected revision, resolves trusted evidence, checks
    the matching transition edge, and commits history. A conflict requires
    reload/reinspection; it never overwrites newer state.
    """
    def __init__(self, *, contract: Mapping[str, Any], identity: Mapping[str, Any],
                 state_store: SubjectStateStore, evidence_store: EvidenceStore,
                 evidence_registry: Optional[Mapping[str, Any]] = None):
        self.identity = dict(identity)
        self.state_store = state_store
        self.evidence_store = evidence_store
        self.engine = TransitionEngine(dict(contract), evidence_registry=evidence_registry,
                                       require_registered=False, evidence_store=evidence_store)
        self.entry_times: Dict[str, str] = {}
        initial = contract.get("initial_state")
        if not isinstance(initial, str) or not initial:
            raise TransitionError("standalone StateWork contract requires initial_state")
        snapshot = state_store.get(identity)
        if snapshot.get("state") is None:
            state_store.commit(identity, expected_revision=0, new_state=initial,
                               transition={"trigger": "controller_initialization",
                                           "to_state": initial})

    def inspect(self) -> Dict[str, Any]:
        return self.state_store.get(self.identity)

    def request_transition(self, *, to_state: str, trigger: str,
                           evidence_refs: Iterable[str], expected_revision: int) -> TransitionDecision:
        snapshot = self.inspect()
        if int(snapshot.get("revision", 0)) != int(expected_revision):
            raise TransitionError(
                f"subject state revision conflict: expected {expected_revision}, "
                f"found {snapshot.get('revision', 0)}; re-inspect required")
        from_state = str(snapshot.get("state"))
        resolved = self.evidence_store.resolve(list(evidence_refs))
        edges = self.engine.matching_edges(from_state, to_state, trigger)
        freshness = (edges[0].get("evidence_freshness") if len(edges) == 1 else {}) or {}
        entry = self.entry_times.get(from_state) or snapshot.get("updated_at")
        if freshness.get("mode") == "after_state_entry" and entry:
            for item in resolved:
                if str(item.get("observed_at")) < str(entry):
                    return TransitionDecision(False, "evidence predates current state entry", from_state, to_state, trigger, list(self.engine.matching_edges(from_state, to_state, trigger)[0].get("required_evidence", [])))
        max_age = freshness.get("max_age_seconds")
        if max_age is not None:
            now = datetime.now(timezone.utc)
            for item in resolved:
                try:
                    observed = datetime.fromisoformat(str(item.get("observed_at")).replace("Z", "+00:00"))
                except ValueError:
                    return TransitionDecision(False, "evidence has invalid observed_at", from_state, to_state, trigger)
                if (now - observed).total_seconds() > int(max_age):
                    return TransitionDecision(False, "evidence exceeds declared freshness", from_state, to_state, trigger)
        decision = self.engine.transition(
            str(self.identity["subject_ref"]), from_state, to_state,
            trigger=trigger, evidence_refs=resolved)
        if not decision.allowed:
            return decision
        transition_record = {"trigger": trigger, "evidence_refs": list(evidence_refs),
                             "decision_reason": decision.reason}
        self.state_store.commit(
            self.identity, expected_revision=expected_revision, new_state=to_state,
            transition=transition_record)
        self.entry_times[from_state] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return decision


@dataclass
class TransitionDecision:
    allowed: bool
    reason: str
    from_state: str
    to_state: str
    trigger: Optional[str] = None
    required_evidence: List[str] = field(default_factory=list)
    evidence_freshness: Dict[str, Any] = field(default_factory=dict)


class TransitionEngine:
    """Machine-readable legality and evidence guards for a StateWork."""

    def __init__(self, contract: Dict[str, Any], *, evidence_registry: Optional[Mapping[str, Any]] = None,
                 require_registered: bool = False, evidence_store: Optional[EvidenceStore] = None) -> None:
        states = contract.get("states")
        transitions = contract.get("transitions")
        if not isinstance(states, list) or not states:
            raise TransitionError("transition contract requires states")
        initial_state = contract.get("initial_state")
        if initial_state is not None and initial_state not in states:
            raise TransitionError("transition contract initial_state is not declared")
        if not isinstance(transitions, list):
            raise TransitionError("transition contract requires transitions")
        if initial_state is None:
            raise TransitionError("transition contract requires initial_state")
        self.states = set(states)
        self.transitions = transitions
        self.completion_states = set(contract.get("completion_states") or [])
        registry = evidence_registry
        if registry is None:
            try:
                registry = load_evidence_kind_registry()
            except (FileNotFoundError, ValueError, jsonschema.ValidationError):
                registry = {"kinds": {}}
        self.evidence_registry = dict((registry or {}).get("kinds") or {})
        self.require_registered = require_registered
        self.evidence_store = evidence_store
        for edge in transitions:
            origin = edge.get("from")
            destination = edge.get("to")
            if origin != "*" and origin not in self.states:
                raise TransitionError(f"transition origin {origin!r} is not declared")
            if destination not in self.states:
                raise TransitionError(f"transition destination {destination!r} is not declared")
            if not edge.get("trigger"):
                raise TransitionError(f"transition {origin!r} -> {destination!r} requires a trigger")
            required = edge.get("required_evidence") or []
            if not required or any(not isinstance(kind, str) or not kind for kind in required):
                raise TransitionError(f"transition {origin!r} -> {destination!r} requires evidence kinds")
            if require_registered:
                missing = [kind for kind in required if kind not in self.evidence_registry]
                if missing:
                    raise TransitionError(
                        f"transition {origin!r} -> {destination!r} uses unregistered evidence kinds: {missing}")

    def _is_consequential(self, edge: Mapping[str, Any], to_state: str) -> bool:
        if edge.get("consequential") is not None:
            return bool(edge["consequential"])
        return any(kind in self.evidence_registry for kind in (edge.get("required_evidence") or ()))

    def _evidence_is_valid(self, kind: str, item: Mapping[str, Any], *, consequential: bool = False) -> bool:
        spec = self.evidence_registry.get(kind)
        if spec is None:
            return (not consequential) or (bool(item.get("content_digest"))
                                            and str(item.get("issuer") or "").startswith("host:"))
        issuer = item.get("issuer")
        schema = item.get("schema")
        validator = item.get("validator")
        if issuer not in set(spec.get("allowed_issuers") or ()) or schema != spec.get("schema") or validator != spec.get("validator"):
            return False
        if consequential and not (item.get("attestation_digest") or item.get("content_digest")):
            return False
        return True


    def transition(self, subject_ref: str, from_state: str, to_state: str, *, trigger: Optional[str] = None,
                   evidence_refs: Iterable[Mapping[str, Any] | str] = ()) -> TransitionDecision:
        if not isinstance(subject_ref, str) or not subject_ref.strip():
            return TransitionDecision(False, "subject_ref required", from_state, to_state, trigger, [])
        if from_state not in self.states or to_state not in self.states:
            return TransitionDecision(False, "unknown state", from_state, to_state, trigger, [])
        matches = self.matching_edges(from_state, to_state, trigger)
        if matches:
            exact = [edge for edge in matches if edge.get("from") == from_state]
            matches = exact or matches  # exact edges explicitly outrank wildcard edges
        if len(matches) > 1:
            return TransitionDecision(False, "ambiguous transition edges", from_state,
                                     to_state, trigger, [])
        for edge in matches:
            required = list(edge.get("required_evidence") or [])
            consequential = self._is_consequential(edge, to_state)
            evidence: List[Mapping[str, Any]] = []
            missing = []
            for item in evidence_refs:
                if isinstance(item, str):
                    if self.evidence_store is None:
                        continue
                    try:
                        evidence.extend(self.evidence_store.resolve([item]))
                    except TransitionError:
                        continue
                elif isinstance(item, Mapping):
                    # Once a trusted store is installed, caller metadata is only
                    # a lookup hint; resolve the reference and use the stored
                    # record for the actual authorization decision.
                    if self.evidence_store is not None and item.get("ref"):
                        try:
                            evidence.extend(self.evidence_store.resolve([str(item["ref"])]))
                        except TransitionError:
                            continue
                    else:
                        evidence.append(item)
            for kind in required:
                valid = [item for item in evidence if isinstance(item, Mapping) and item.get("kind") == kind and item.get("ref") and item.get("subject_ref") == subject_ref and item.get("observed_at") and item.get("invalidated") is not True and self._evidence_is_valid(kind, item, consequential=consequential)]
                if not valid:
                    missing.append(kind)
            if missing:
                return TransitionDecision(
                    False, f"missing evidence kinds: {', '.join(missing)}", from_state,
                    to_state, trigger, required, dict(edge.get("evidence_freshness") or {}))
            return TransitionDecision(True, "allowed", from_state, to_state, trigger,
                                      required, dict(edge.get("evidence_freshness") or {}))
        return TransitionDecision(False, "transition not declared", from_state, to_state, trigger, [])

    def matching_edges(self, from_state: str, to_state: str,
                       trigger: Optional[str]) -> List[Dict[str, Any]]:
        matches = []
        for edge in self.transitions:
            if edge.get("from") not in (from_state, "*") or edge.get("to") != to_state:
                continue
            edge_trigger = edge.get("trigger")
            if edge_trigger is not None and edge_trigger != trigger:
                continue
            matches.append(edge)
        if matches:
            exact = [edge for edge in matches if edge.get("from") == from_state]
            matches = exact or matches
        return matches


class StandaloneHostInterface:
    """Small host facade for enforcing installations."""
    def __init__(self, *, root: Path, state_path: Optional[Path] = None,
                 evidence_path: Optional[Path] = None) -> None:
        self.root = Path(root)
        self.evidence_path = Path(evidence_path) if evidence_path else self.root / "state" / "evidence.json"
        self.state_store = SubjectStateStore(Path(state_path) if state_path else self.root / "state" / "subjects.json")
        self.evidence_store = EvidenceStore()
        self._controllers: Dict[str, StandaloneStateWorkController] = {}
        self._controller_contract_hashes: Dict[str, str] = {}
        self._load_evidence()

    def _load_evidence(self) -> None:
        if not self.evidence_path or not self.evidence_path.exists():
            return
        try:
            data = json.loads(self.evidence_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TransitionError("trusted evidence store is unreadable") from exc
        if not isinstance(data, list):
            raise TransitionError("trusted evidence store must contain a list")
        for record in data:
            self.evidence_store.put(record)

    def resolve_statework(self, statework_id: str) -> Dict[str, Any]:
        registry = _load_yaml(self.root / "registry.yaml")
        if statework_id not in set((registry or {}).get("stateworks", [])):
            raise TransitionError(f"unknown StateWork {statework_id!r}")
        base = self.root / statework_id
        return {"id": statework_id, "manifest": _load_yaml(base / "manifest.yaml"),
                "contract": _load_yaml(base / "transitions.yaml")}

    def start_or_resume(self, *, statework_id: str, identity: Mapping[str, Any]) -> Dict[str, Any]:
        if identity.get("statework_id") != statework_id:
            raise TransitionError("requested StateWork does not match the subject identity")
        statework = self.resolve_statework(statework_id)
        contract = statework["contract"]
        contract_hash = hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        key = SubjectStateStore.key(identity)
        controller = self._controllers.get(key)
        if controller is None or self._controller_contract_hashes.get(key) != contract_hash:
            registry = load_evidence_kind_registry(self.root / "schemas" / "evidence-kinds.yaml")
            controller = StandaloneStateWorkController(contract=contract, identity=identity,
                                                       state_store=self.state_store,
                                                       evidence_store=self.evidence_store,
                                                       evidence_registry=registry)
            self._controllers[key] = controller
            self._controller_contract_hashes[key] = contract_hash
        return controller.inspect()

    def submit_attested_observation(self, record: Mapping[str, Any]) -> str:
        ref = self.evidence_store.put(record)
        self.evidence_store.save(self.evidence_path)
        return ref

    def publish_packet(self, packet: Mapping[str, Any], *, storage_path: Optional[Path] = None) -> str:
        """Publish a validated handoff packet through CSW's typed store."""
        if not isinstance(packet, Mapping):
            raise TransitionError("handoff packet must be a mapping")
        store = PacketStore(packet_registry_path=self.root / "schemas" / "packet-registry.yaml",
                            storage_path=storage_path)
        return store.put(dict(packet))

    def recover_from_invalidation(self, *, evidence_ref: str, identity: Mapping[str, Any],
                                 statework_id: str) -> Dict[str, Any]:
        """Record trusted invalidation and return the authoritative reinspection state."""
        self.evidence_store.invalidate(evidence_ref)
        self.evidence_store.save(self.evidence_path)
        return self.start_or_resume(statework_id=statework_id, identity=identity)

    def request_transition(self, *, statework_id: str, identity: Mapping[str, Any],
                           to_state: str, trigger: str, evidence_refs: Iterable[str],
                           expected_revision: int) -> TransitionDecision:
        self.start_or_resume(statework_id=statework_id, identity=identity)
        controller = self._controllers[SubjectStateStore.key(identity)]
        return controller.request_transition(to_state=to_state, trigger=trigger,
                                              evidence_refs=evidence_refs,
                                              expected_revision=expected_revision)
