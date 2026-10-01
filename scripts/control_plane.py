#!/usr/bin/env python3
"""Validated packet and transition primitives for CognitiveStateWork."""
from __future__ import annotations

import json
import copy
import fcntl
import hashlib
import inspect
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional
from datetime import datetime, timezone

import jsonschema
import yaml
from importlib.resources import files as resource_files
try:
    from .workflow_engines import (EngineRegistry, MilestoneWorkflowEngine,
                                   StateMachineWorkflowEngine, WorkflowDecision,
                                   WorkflowIdentity, WorkflowProgressFact,
                                   WorkflowSnapshot)
    from .flow_selectors import FlowSelector
except ImportError:
    from workflow_engines import (EngineRegistry, MilestoneWorkflowEngine,
                                  StateMachineWorkflowEngine, WorkflowDecision,
                                  WorkflowIdentity, WorkflowProgressFact,
                                  WorkflowSnapshot)
    from flow_selectors import FlowSelector

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


def render_runtime_capsule(manifest: Mapping[str, Any], *, engine_kind: str,
                           contract_version: str, flows: Iterable[str],
                           guidance: str = "") -> str:
    """Render compact runtime guidance from machine-owned bundle metadata."""
    lines = [f"# {manifest.get('name') or manifest.get('id')} — StateWork",
             f"Domain: {manifest.get('domain') or 'unspecified'}",
             f"Purpose: {manifest.get('purpose') or 'unspecified'}",
             f"Workflow engine: {engine_kind} ({contract_version})"]
    flow_names = tuple(sorted(set(str(item) for item in flows if item)))
    if flow_names:
        lines.extend(["Available flows:", *[f"- {name}" for name in flow_names]])
    lines.extend([
        "Inspect current workflow progress and eligible steps through the host workflow authority.",
        "Use the selected flow as guidance; the workflow contract and host authority determine legal steps.",
    ])
    if guidance.strip():
        lines.extend(["", "## Domain guidance", "", guidance.strip()])
    return "\n".join(lines) + "\n"


def _aware_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be non-empty date-time text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp is not a valid date-time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


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


def load_packet_registry(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the host's merged packet declarations and validate their envelope."""
    if path is None:
        resource = _package_resource("schemas/packet-registry.yaml")
        data = yaml.safe_load(resource.read_text(encoding="utf-8")) if resource else _load_yaml(
            ROOT / "schemas" / "packet-registry.yaml")
        schema = json.loads(_schema_text("packet-registry.schema.json"))
    else:
        path = Path(path)
        data = _load_yaml(path)
        schema_path = path.with_name("packet-registry.schema.json")
        schema = (json.loads(schema_path.read_text(encoding="utf-8"))
                  if schema_path.exists() else json.loads(_schema_text("packet-registry.schema.json")))
    jsonschema.validate(instance=data, schema=schema)
    return dict(data)


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


class FreshnessValidatorRegistry:
    """Explicit host-trusted registry for specialized freshness checks."""
    def __init__(self) -> None:
        self._validators: Dict[str, Any] = {}
        self._hashes: Dict[str, str] = {}

    def register(self, validator_id: str, implementation: Any, *,
                 implementation_hash: str, trusted: bool = False) -> None:
        if not trusted:
            raise PermissionError("freshness validator registration requires explicit host trust")
        if not validator_id or len(validator_id) > 128 or not callable(implementation):
            raise ValueError("freshness validator registration is malformed")
        if len(implementation_hash) != 64 or any(
                char not in "0123456789abcdef" for char in implementation_hash):
            raise ValueError("freshness validator implementation hash must be SHA-256")
        prior = self._hashes.get(validator_id)
        if prior is not None and prior != implementation_hash:
            raise ValueError(f"freshness validator {validator_id!r} is already registered differently")
        self._validators[validator_id] = implementation
        self._hashes[validator_id] = implementation_hash

    def validate(self, validator_id: str, packet: Dict[str, Any],
                 context: Mapping[str, Any]) -> bool:
        implementation = self._validators.get(validator_id)
        return bool(implementation and implementation(packet, context))

    @property
    def identities(self) -> Mapping[str, str]:
        return dict(self._hashes)


def _trusted_validator_hash(function: Any) -> str:
    return hashlib.sha256(inspect.getsource(function).encode("utf-8")).hexdigest()


FRESHNESS_VALIDATORS = FreshnessValidatorRegistry()
FRESHNESS_VALIDATORS.register(
    "repository_truth_v1", _repository_truth_v1,
    implementation_hash=_trusted_validator_hash(_repository_truth_v1), trusted=True)


def _path_value(value: Mapping[str, Any], path: str) -> Any:
    current: Any = value
    for part in path.split("."):
        if not part or part.startswith("_") or not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def evaluate_freshness(packet: Dict[str, Any], context: Mapping[str, Any],
                       rule: Any, *, _depth: int = 0) -> bool:
    """Evaluate bounded data-only freshness rules or a trusted validator ID."""
    if _depth > 8:
        return False
    if rule == "immutable":
        return True
    if isinstance(rule, str):
        return FRESHNESS_VALIDATORS.validate(rule, packet, context)
    if not isinstance(rule, Mapping):
        return False
    strategy = rule.get("strategy")
    if strategy == "trusted_validator":
        return FRESHNESS_VALIDATORS.validate(
            str(rule.get("validator_id") or ""), packet, context)
    if strategy == "exact_context":
        packet_path, context_path = rule.get("packet_path"), rule.get("context_path")
        if not isinstance(packet_path, str) or not isinstance(context_path, str):
            return False
        expected = _path_value(context, context_path)
        return expected is not None and _path_value(packet, packet_path) == expected
    if strategy == "vector_match":
        packet_path, context_path = rule.get("packet_path"), rule.get("context_path")
        fields = rule.get("fields")
        if (not isinstance(packet_path, str) or not isinstance(context_path, str)
                or not isinstance(fields, list) or not fields or len(fields) > 32):
            return False
        actual, expected = _path_value(packet, packet_path), _path_value(context, context_path)
        return (isinstance(actual, Mapping) and isinstance(expected, Mapping)
                and all(isinstance(field, str) and field in expected
                        and actual.get(field) == expected.get(field) for field in fields))
    if strategy == "max_age":
        observed = _path_value(packet, str(rule.get("timestamp_path") or "observed_at"))
        try:
            age = (datetime.now(timezone.utc) - _aware_datetime(observed)).total_seconds()
            maximum = float(rule.get("seconds"))
        except (TypeError, ValueError):
            return False
        return 0 <= age <= maximum
    if strategy == "all":
        rules = rule.get("rules")
        return (isinstance(rules, list) and 1 <= len(rules) <= 16
                and all(evaluate_freshness(packet, context, child, _depth=_depth + 1)
                        for child in rules))
    return False


class EvidenceStore:
    """Trusted evidence authority with immutable revisions and locked merge."""
    def __init__(self, records: Optional[Iterable[Mapping[str, Any]]] = ()) -> None:
        self._records: Dict[str, Dict[str, Any]] = {}
        for record in records or ():
            self.create(record)

    @staticmethod
    def _digest(record: Mapping[str, Any]) -> str:
        # The attestation covers the complete revision and invalidation history.
        body = {key: value for key, value in dict(record).items()
                if key != "attestation_digest"}
        body["invalidated"] = body.get("invalidated") is True
        return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

    def _current_body(self, record: Mapping[str, Any]) -> Dict[str, Any]:
        return {key: value for key, value in dict(record).items() if key not in {"revisions", "invalidation_events"}}

    @staticmethod
    def _validate_shape(record: Mapping[str, Any]) -> None:
        if not isinstance(record, Mapping):
            raise TransitionError("trusted evidence record must be a mapping")
        ref = record.get("ref")
        kind = record.get("kind")
        if not isinstance(ref, str) or not ref or not isinstance(kind, str) or not kind:
            raise TransitionError("trusted evidence requires ref and kind")

    def create(self, record: Mapping[str, Any]) -> str:
        """Create host-attested evidence; only this path may mint a digest."""
        self._validate_shape(record)
        candidate = self._current_body(record)
        supplied = record.get("attestation_digest")
        expected = self._digest(candidate)
        if supplied is not None and supplied != expected:
            raise TransitionError("supplied evidence attestation digest does not match content")
        prior = self._records.get(str(record["ref"]))
        if prior is not None and self._digest(self._current_body(prior)) != expected:
            raise TransitionError(f"evidence reference {record['ref']!r} has conflicting trusted content")
        if prior is None:
            candidate["revisions"] = [dict(candidate)]
            candidate["invalidation_events"] = list(record.get("invalidation_events") or [])
        else:
            candidate["revisions"] = list(prior.get("revisions") or [self._current_body(prior)])
            candidate["invalidation_events"] = list(prior.get("invalidation_events") or [])
        candidate["attestation_digest"] = self._digest(candidate)
        self._records[str(record["ref"])] = candidate
        return str(record["ref"])

    def put(self, record: Mapping[str, Any]) -> str:
        """Load already-attested evidence after verifying its persisted digest."""
        self._validate_shape(record)
        supplied = record.get("attestation_digest")
        if not isinstance(supplied, str) or self._digest(record) != supplied:
            raise TransitionError(f"evidence reference {record.get('ref')!r} has an invalid attestation digest")
        stored = self._records.get(str(record.get("ref") or ""))
        if stored is not None and stored.get("attestation_digest") != supplied:
            raise TransitionError("persisted evidence revision conflicts with trusted history")
        if stored is None:
            self._records[str(record["ref"])] = dict(record)
        return str(record["ref"])

    @classmethod
    def load_attested(cls, records: Iterable[Mapping[str, Any]]) -> "EvidenceStore":
        """Load persisted records only after verifying their original digest."""
        store = cls()
        for record in records:
            store.put(record)
        return store

    def resolve(self, refs: Iterable[str]) -> List[Dict[str, Any]]:
        out = []
        for ref in refs:
            record = self._records.get(str(ref))
            if record is None:
                raise TransitionError(f"evidence reference {ref!r} is not present in the trusted store")
            current = self._current_body(record)
            if self._digest(record) != record.get("attestation_digest"):
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
                    persisted = EvidenceStore.load_attested(
                        json.loads(path.read_text(encoding="utf-8")))
                except (OSError, json.JSONDecodeError, TransitionError) as exc:
                    raise TransitionError("trusted evidence store is unreadable") from exc
            for ref, record in self._records.items():
                if ref not in persisted._records:
                    persisted._records[ref] = dict(record)
                    continue
                left = persisted._records[ref]
                right = record
                for item in (left, right):
                    body = self._current_body(item)
                    if self._digest(item) != item.get("attestation_digest"):
                        raise TransitionError(f"evidence reference {ref!r} has an invalid merge revision")
                left_base = self._current_body(left)
                right_base = self._current_body(record)
                left_base["invalidated"] = False
                right_base["invalidated"] = False
                if self._digest(left_base) != self._digest(right_base):
                    raise TransitionError(f"evidence reference {ref!r} conflicts during merge")
                left_revisions = list(left.get("revisions") or [])
                for revision in list(right.get("revisions") or []):
                    if revision not in left_revisions:
                        left_revisions.append(dict(revision))
                left_events = list(left.get("invalidation_events") or [])
                event_keys = {json.dumps(item, sort_keys=True, default=str) for item in left_events}
                for event in list(right.get("invalidation_events") or []):
                    key = json.dumps(event, sort_keys=True, default=str)
                    if key not in event_keys:
                        left_events.append(dict(event)); event_keys.add(key)
                left["revisions"] = left_revisions
                left["invalidation_events"] = left_events
                left["invalidated"] = bool(left.get("invalidated") or record.get("invalidated"))
                left["attestation_digest"] = self._digest(left)
            fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(list(persisted._records.values()), stream, sort_keys=True, separators=(",", ":"), default=str)
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
        fields = [identity.get(name) for name in (
            "namespace_id", "application_id", "application_instance_id",
            "workflow_id", "subject_ref", "statework_id", "contract_version")]
        if any(not isinstance(value, str) or not value for value in fields):
            raise TransitionError(
                "subject state identity requires namespace, application, application instance, "
                "workflow, subject, StateWork, and contract version")
        return json.dumps(dict(zip((
            "namespace_id", "application_id", "application_instance_id",
            "workflow_id", "subject_ref", "statework_id", "contract_version"), fields)),
            sort_keys=True, separators=(",", ":"))

    def _refresh(self) -> None:
        if self.path.exists():
            self._load()

    def get(self, identity: Mapping[str, Any]) -> Dict[str, Any]:
        self._refresh()
        return dict(self._data["subjects"].get(self.key(identity)) or {"state": None, "revision": 0})

    def initialize_workflow(self, identity: Mapping[str, Any], *, engine_kind: str,
                            initial_data: Mapping[str, Any]) -> Dict[str, Any]:
        key = self.key(identity)
        self.lock_path.touch(mode=0o600, exist_ok=True)
        with self.lock_path.open("r+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            self._refresh()
            current = self._data["subjects"].get(key)
            if current is None:
                current = dict(identity)
                current.update({"engine_kind": engine_kind,
                                "workflow_data": copy.deepcopy(dict(initial_data)),
                                "revision": 0,
                                "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})
                self._data["subjects"][key] = current
                self._save()
            elif current.get("engine_kind", engine_kind) != engine_kind:
                raise TransitionError("workflow engine kind differs from persisted identity")
            return dict(current)

    def commit_workflow(self, identity: Mapping[str, Any], *, expected_revision: int,
                        engine_kind: str, workflow_data: Mapping[str, Any],
                        transition: Mapping[str, Any]) -> Dict[str, Any]:
        key = self.key(identity)
        self.lock_path.touch(mode=0o600, exist_ok=True)
        with self.lock_path.open("r+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            self._refresh()
            current = self._data["subjects"].get(key) or {"revision": 0}
            if int(current.get("revision", 0)) != int(expected_revision):
                raise TransitionError(
                    f"workflow revision conflict: expected {expected_revision}, "
                    f"found {current.get('revision', 0)}; re-inspect required")
            if current.get("engine_kind", engine_kind) != engine_kind:
                raise TransitionError("workflow engine kind differs from persisted identity")
            revision = int(expected_revision) + 1
            updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            record = dict(identity)
            record.update({"engine_kind": engine_kind,
                           "workflow_data": copy.deepcopy(dict(workflow_data)),
                           "revision": revision, "updated_at": updated_at})
            self._data["subjects"][key] = record
            self._data["history"].append({
                "identity": dict(identity), "engine_kind": engine_kind,
                "revision": revision, "recorded_at": updated_at,
                "transition": copy.deepcopy(dict(transition))})
            self._save()
            return dict(record)

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
            recorded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            self._data["history"].append({"identity": dict(identity), "from_state": current.get("state"), "to_state": new_state, "revision": revision, "recorded_at": recorded_at, "transition": dict(transition)})
            self._save()
            return record


class PacketStore:
    """Validated typed handoff packets. Presence alone is never truth."""

    def __init__(self, packets: Optional[Iterable[Dict[str, Any]]] = None,
                 packet_registry_path: Optional[Path] = None,
                 storage_path: Optional[Path] = None,
                 secure_storage_dir: bool = False,
                 packet_registry_data: Optional[Mapping[str, Any]] = None,
                 packet_schemas: Optional[Mapping[str, Mapping[str, Any]]] = None) -> None:
        registry_path = packet_registry_path
        if packet_registry_data is not None:
            data = dict(packet_registry_data)
            registry_schema_text = _schema_text("packet-registry.schema.json")
        elif registry_path is None:
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
        self.packet_schemas = {str(key): dict(value)
                               for key, value in (packet_schemas or {}).items()}
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
        schema = self.packet_schemas.get(str(packet_type))
        if schema is None:
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
        freshness = meta.get("freshness")
        if freshness is None and meta.get("freshness_validator"):
            freshness = {"strategy": "trusted_validator",
                         "validator_id": meta.get("freshness_validator")}
        if freshness == "immutable":
            return True
        required_context = list(meta.get("required_context") or [])
        required_any_context = list(meta.get("required_any_context") or [])
        if required_context and not all(context.get(key) for key in required_context):
            return False
        if required_any_context and not any(context.get(key) for key in required_any_context):
            return False
        return evaluate_freshness(packet, context, freshness)

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
                                       require_registered=True, evidence_store=evidence_store)
        self.entry_times: Dict[str, str] = {}
        initial = contract.get("initial_state")
        if not isinstance(initial, str) or not initial:
            raise TransitionError("standalone StateWork contract requires initial_state")
        snapshot = state_store.get(identity)
        if snapshot.get("state") is None:
            try:
                state_store.commit(identity, expected_revision=0, new_state=initial,
                                   transition={"trigger": "controller_initialization",
                                               "to_state": initial})
            except TransitionError as exc:
                if "revision conflict" not in str(exc):
                    raise
                snapshot = state_store.get(identity)
                if snapshot.get("state") is None:
                    raise
        current = state_store.get(identity)
        for item in reversed(state_store._data.get("history") or []):
            identity_key = state_store.key(identity)
            if state_store.key(item.get("identity") or {}) != identity_key:
                continue
            state_name = str(item.get("to_state") or "")
            recorded_at = str(item.get("recorded_at") or "")
            if state_name and recorded_at:
                self.entry_times[state_name] = recorded_at
        self.entry_times[str(current.get("state") or initial)] = str(current.get("updated_at") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))

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
        references = list(evidence_refs)
        resolved = self.evidence_store.resolve(references)
        edges = self.engine.matching_edges(from_state, to_state, trigger)
        freshness = (edges[0].get("evidence_freshness") if len(edges) == 1 else {}) or {}
        entry = self.entry_times.get(from_state) or snapshot.get("updated_at")
        required_kinds = set(edges[0].get("required_evidence") or []) if len(edges) == 1 else set()
        relevant = [item for item in resolved if item.get("kind") in required_kinds]
        if freshness.get("mode") == "after_state_entry" and entry:
            try:
                entry_at = _aware_datetime(entry)
                for item in relevant:
                    if _aware_datetime(item.get("observed_at")) < entry_at:
                        return TransitionDecision(
                            False, "evidence predates current state entry", from_state,
                            to_state, trigger, list(edges[0].get("required_evidence", [])))
            except ValueError as exc:
                return TransitionDecision(False, str(exc), from_state, to_state, trigger)
        max_age = freshness.get("max_age_seconds")
        if max_age is not None:
            now = datetime.now(timezone.utc)
            for item in relevant:
                try:
                    observed = _aware_datetime(item.get("observed_at"))
                except ValueError as exc:
                    return TransitionDecision(False, str(exc), from_state, to_state, trigger)
                if (now - observed).total_seconds() > int(max_age):
                    return TransitionDecision(False, "evidence exceeds declared freshness", from_state, to_state, trigger)
        decision = self.engine.transition(
            str(self.identity["subject_ref"]), from_state, to_state,
            trigger=trigger, evidence_refs=resolved)
        if not decision.allowed:
            return decision
        transition_record = {"trigger": trigger, "evidence_refs": references,
                             "decision_reason": decision.reason,
                             "progress": decision.progress_facts()}
        self.state_store.commit(
            self.identity, expected_revision=expected_revision, new_state=to_state,
            transition=transition_record)
        committed = self.state_store.get(self.identity)
        self.entry_times[to_state] = str(committed.get("updated_at") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        return decision


PROGRESS_CLASSES = {
    "FORWARD_PROGRESS", "LATERAL", "RECOVERY", "INVALIDATION", "REGRESSION",
    "TERMINAL",
}


@dataclass
class TransitionDecision:
    allowed: bool
    reason: str
    from_state: str
    to_state: str
    trigger: Optional[str] = None
    required_evidence: List[str] = field(default_factory=list)
    evidence_freshness: Dict[str, Any] = field(default_factory=dict)
    # Progress metadata. CFW uses this to distinguish real forward progress
    # from a recovery cycle that merely moved the state machine, so a
    # recovery hop does not silently reset the task's no-progress budget.
    edge_id: Optional[str] = None
    path_class: Optional[str] = None
    progress_class: str = "LATERAL"
    work_class: Optional[str] = None
    domain_effect: Optional[str] = None
    normal_path_rank_before: Optional[int] = None
    normal_path_rank_after: Optional[int] = None

    def progress_facts(self) -> Dict[str, Any]:
        return {"edge_id": self.edge_id, "path_class": self.path_class,
                "progress_class": self.progress_class,
                "work_class": self.work_class, "domain_effect": self.domain_effect,
                "normal_path_rank_before": self.normal_path_rank_before,
                "normal_path_rank_after": self.normal_path_rank_after}

    def is_forward_progress(self) -> bool:
        return self.progress_class in {"FORWARD_PROGRESS", "TERMINAL"}


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
        self.normal_path = list(contract.get("normal_path") or [])
        self._normal_rank = {state: index for index, state in enumerate(self.normal_path)}
        registry = evidence_registry
        if registry is None:
            try:
                registry = load_evidence_kind_registry()
            except (FileNotFoundError, ValueError, jsonschema.ValidationError):
                registry = {"kinds": {}}
        self.evidence_registry = dict((registry or {}).get("kinds") or {})
        self.require_registered = require_registered
        self.evidence_store = evidence_store
        edge_ids: set[str] = set()
        for edge in transitions:
            edge_id = edge.get("id")
            if not isinstance(edge_id, str) or not edge_id.strip() or len(edge_id) > 128:
                raise TransitionError("every transition requires a stable bounded id")
            if edge_id in edge_ids:
                raise TransitionError(f"duplicate transition id {edge_id!r}")
            edge_ids.add(edge_id)
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
            if (not edge.get("work_class") or not edge.get("domain_effect")
                    or edge.get("progress_class") not in PROGRESS_CLASSES):
                raise TransitionError(
                    f"transition {edge_id!r} requires work_class, domain_effect, and progress_class")
            path_class = edge.get("path_class")
            if path_class is not None and path_class not in {
                    "normal", "recovery", "failure", "invalidation", "external"}:
                raise TransitionError(f"transition {edge_id!r} has an unsupported path_class")
            if edge.get("path_class") == "external" and edge.get("progress_class") != "INVALIDATION":
                raise TransitionError("external transitions must classify progress as INVALIDATION")
            if (path_class in {"failure", "invalidation"}
                    and edge.get("progress_class") not in {"INVALIDATION", "TERMINAL"}):
                raise TransitionError(
                    "failure and invalidation paths must classify progress as INVALIDATION unless terminal")
            if path_class == "recovery" and edge.get("progress_class") not in {"RECOVERY", "TERMINAL"}:
                raise TransitionError("recovery paths must classify progress as RECOVERY or TERMINAL")
            entering_completion = destination in self.completion_states
            if entering_completion != (edge.get("progress_class") == "TERMINAL"):
                raise TransitionError(
                    f"transition {edge_id!r} must classify completion-state entry as TERMINAL")
            if require_registered and self._is_consequential(edge, str(destination)):
                missing = [kind for kind in required if kind not in self.evidence_registry]
                if missing:
                    raise TransitionError(
                        f"consequential transition {edge_id!r} uses unregistered evidence kinds: {missing}")

    def _progress_facts(self, edge: Mapping[str, Any], from_state: str,
                        to_state: str) -> Dict[str, Any]:
        """Classify a transition so CFW can bound recovery loops."""
        before = self._normal_rank.get(from_state)
        after = self._normal_rank.get(to_state)
        path_class = str(edge.get("path_class") or ("normal" if after is not None else "unranked"))
        progress_class = str(edge["progress_class"])
        return {"edge_id": edge["id"],
                "path_class": path_class,
                "progress_class": progress_class,
                "work_class": str(edge["work_class"]),
                "domain_effect": str(edge["domain_effect"]),
                "normal_path_rank_before": before,
                "normal_path_rank_after": after}

    def _is_consequential(self, edge: Mapping[str, Any], to_state: str) -> bool:
        return edge.get("consequential") is True

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
                                      required, dict(edge.get("evidence_freshness") or {}),
                                      **self._progress_facts(edge, from_state, to_state))
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


class WorkflowAuthority:
    """Generic host authority over compiled StateWork workflow engines.

    Engine choice and step semantics stay inside CSW. Consumers inspect a
    normalized snapshot and submit an engine-neutral step identifier.
    """
    def __init__(self, *, root: Optional[Path] = None,
                 state_store: Optional[SubjectStateStore] = None,
                 evidence_store: Optional[EvidenceStore] = None,
                 engine_registry: Optional[EngineRegistry] = None):
        self.root = Path(root or ROOT)
        self.state_store = state_store or SubjectStateStore(
            self.root / "state" / "subjects.json")
        self.evidence_store = evidence_store or EvidenceStore()
        self.engine_registry = engine_registry or EngineRegistry()
        self._controllers: Dict[str, StandaloneStateWorkController] = {}

    def _bundle(self, statework_id: str, contract_hash: Optional[str] = None
                ) -> tuple[dict[str, Any], dict[str, Any], str, Any, dict[str, Any]]:
        compiled = load_compiled_registry(self.root)
        entry = next((item for item in compiled.get("stateworks") or ()
                      if item.get("id") == statework_id), None)
        if entry is None:
            raise TransitionError(f"StateWork {statework_id!r} is unavailable")
        manifest = dict(entry.get("manifest") or {})
        engine_decl = manifest.get("engine") or {
            "kind": "state_machine", "contract": "transitions.yaml",
            "contract_version": StateMachineWorkflowEngine.contract_version}
        if not isinstance(engine_decl, Mapping):
            raise TransitionError("StateWork engine declaration must be a mapping")
        kind = str(engine_decl.get("kind") or "")
        engine_pin = dict(entry.get("engine") or {})
        contract_name = str(engine_pin.get("contract_path") or engine_decl.get("contract") or "")
        if (not contract_name or Path(contract_name).is_absolute()
                or ".." in Path(contract_name).parts):
            raise TransitionError("workflow contract path escapes its bundle")
        bundle_root = Path(str(entry.get("bundle_root") or "")).resolve()
        if not bundle_root.is_dir():
            raise TransitionError(f"StateWork {statework_id!r} bundle root is unavailable")
        contract_path = (bundle_root / contract_name).resolve()
        try:
            contract_path.relative_to(bundle_root)
        except ValueError as exc:
            raise TransitionError("workflow contract path escapes its bundle") from exc
        if not contract_path.is_file():
            raise TransitionError("workflow contract is missing")
        contract = _load_yaml(contract_path) or {}
        digest = hashlib.sha256(json.dumps(
            contract, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        if contract_hash and contract_hash != digest:
            raise TransitionError("workflow contract differs from the CFW policy pin")
        if engine_pin.get("contract_hash") and engine_pin["contract_hash"] != digest:
            raise TransitionError("workflow contract differs from the compiled registry pin")
        evidence_registry = dict(compiled.get("evidence_registry") or {"kinds": {}})
        if kind == "state_machine":
            transition_engine = TransitionEngine(
                dict(contract), evidence_registry=evidence_registry,
                require_registered=True, evidence_store=self.evidence_store)
            engine = StateMachineWorkflowEngine(transition_engine)
        elif kind == "milestone":
            engine = MilestoneWorkflowEngine()
        else:
            engine = self.engine_registry.get(kind)
        engine.validate_contract(contract)
        return manifest, dict(contract), digest, engine, evidence_registry

    @staticmethod
    def _identity(value: WorkflowIdentity | Mapping[str, Any]) -> WorkflowIdentity:
        if isinstance(value, WorkflowIdentity):
            return value
        return WorkflowIdentity(**{key: str(value[key]) for key in (
            "namespace_id", "application_id", "application_instance_id",
            "workflow_id", "subject_ref", "statework_id", "contract_version")})

    def workflow_contract_identity(self, statework_id: str,
                                   contract_hash: Optional[str] = None) -> dict[str, Any]:
        manifest, contract, digest, engine, _evidence_registry = self._bundle(
            statework_id, contract_hash)
        return {"statework_id": statework_id, "engine_kind": engine.kind,
                "contract_version": engine.contract_version,
                "contract_hash": digest, "contract": contract,
                "manifest": manifest}

    def _identity_key(self, identity: WorkflowIdentity) -> str:
        return self.state_store.key(identity.__dict__)

    def _engine_snapshot(self, identity: WorkflowIdentity, contract_hash: str
                         ) -> tuple[Any, dict[str, Any], WorkflowSnapshot]:
        manifest, contract, _digest, engine, evidence_registry = self._bundle(
            identity.statework_id, contract_hash)
        record = self.state_store.get(identity.__dict__)
        if engine.kind == "state_machine":
            key = self._identity_key(identity)
            controller = self._controllers.get(key)
            if controller is None:
                controller = StandaloneStateWorkController(
                    contract=contract, identity=identity.__dict__,
                    state_store=self.state_store, evidence_store=self.evidence_store,
                    evidence_registry=evidence_registry)
                self._controllers[key] = controller
                record = controller.inspect()
            snapshot = engine.inspect(identity, contract,
                                      {"state": record.get("state")},
                                      int(record.get("revision", 0) or 0))
        else:
            initial = engine.initialize(identity, contract)
            record = self.state_store.initialize_workflow(
                identity.__dict__, engine_kind=engine.kind, initial_data=initial)
            data = record.get("workflow_data") or initial
            snapshot = engine.inspect(identity, contract, data,
                                      int(record.get("revision", 0) or 0))
        return engine, contract, snapshot

    def inspect_workflow(self, identity: WorkflowIdentity | Mapping[str, Any], *,
                         contract_hash: str) -> WorkflowSnapshot:
        identity = self._identity(identity)
        _engine, _contract, snapshot = self._engine_snapshot(identity, contract_hash)
        return snapshot

    def eligible_steps(self, identity: WorkflowIdentity | Mapping[str, Any], *,
                       contract_hash: str) -> tuple[Any, ...]:
        return self.inspect_workflow(identity, contract_hash=contract_hash).eligible_steps

    def resolve_legacy_step(self, identity: WorkflowIdentity | Mapping[str, Any], *,
                            contract_hash: str, to_state: str,
                            trigger: Optional[str]) -> str:
        identity = self._identity(identity)
        engine, contract, snapshot = self._engine_snapshot(identity, contract_hash)
        if not isinstance(engine, StateMachineWorkflowEngine):
            raise TransitionError("legacy state transition API is only available for state_machine")
        return engine.resolve_legacy_step(
            contract, current_state=str(snapshot.current_state),
            to_state=to_state, trigger=trigger)

    def apply_step(self, identity: WorkflowIdentity | Mapping[str, Any], *,
                   contract_hash: str, step_id: str, evidence_refs: Iterable[str],
                   expected_revision: int) -> WorkflowDecision:
        identity = self._identity(identity)
        engine, contract, snapshot = self._engine_snapshot(identity, contract_hash)
        if snapshot.revision != int(expected_revision):
            raise TransitionError(
                f"workflow revision conflict: expected {expected_revision}, "
                f"found {snapshot.revision}; re-inspect required")
        references = list(evidence_refs)
        evidence = self.evidence_store.resolve(references)
        decision = engine.apply(identity, contract, snapshot,
                                step_id=step_id, evidence=evidence)
        if not decision.allowed:
            return decision
        if engine.kind == "state_machine":
            edge = next(item for item in contract.get("transitions") or ()
                        if item.get("id") == step_id)
            key = self._identity_key(identity)
            controller = self._controllers[key]
            committed = controller.request_transition(
                to_state=str(edge["to"]), trigger=str(edge.get("trigger") or ""),
                evidence_refs=references, expected_revision=expected_revision)
            if not committed.allowed:
                return WorkflowDecision(
                    False, committed.reason, engine.kind, step_id,
                    expected_revision, expected_revision,
                    str(committed.work_class or edge.get("work_class") or "workflow"),
                    str(committed.domain_effect or edge.get("domain_effect") or "workflow_state"),
                    str(committed.progress_class), snapshot.current_state,
                    snapshot.current_state, snapshot.completed, tuple(references),
                    {"state": snapshot.current_state})
            return decision
        try:
            committed = self.state_store.commit_workflow(
                identity.__dict__, expected_revision=expected_revision,
                engine_kind=engine.kind, workflow_data=decision.state_data,
                transition=decision.to_dict())
        except TransitionError:
            raise
        return WorkflowDecision(
            decision.allowed, decision.reason, decision.engine_kind, decision.step_id,
            expected_revision, int(committed["revision"]), decision.work_class,
            decision.domain_effect, decision.progress_class, decision.current_state,
            decision.previous_state, decision.completed, decision.evidence_refs,
            decision.state_data)

    @staticmethod
    def progress_fact(identity: WorkflowIdentity | Mapping[str, Any],
                      decision: WorkflowDecision) -> WorkflowProgressFact:
        identity = WorkflowAuthority._identity(identity)
        return WorkflowProgressFact(
            statework_id=identity.statework_id, subject_ref=identity.subject_ref,
            engine_kind=decision.engine_kind, step_id=decision.step_id,
            revision=decision.revision, progress_class=decision.progress_class,
            completed=decision.completed, evidence_refs=decision.evidence_refs)


class RegistryCompiler:
    """Compile trusted bundle roots into one immutable, content-addressed registry."""
    VERSION = "2.0.0"

    def __init__(self, root: Optional[Path] = None, *,
                 engine_registry: Optional[EngineRegistry] = None):
        self.root = Path(root or ROOT).resolve()
        self.engine_registry = engine_registry or EngineRegistry()

    @staticmethod
    def _digest(value: Any) -> str:
        return hashlib.sha256(json.dumps(
            value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

    @staticmethod
    def _builtin_engine_hashes() -> dict[str, str]:
        engine_bytes = Path(__file__).with_name("workflow_engines.py").read_bytes()
        selector_bytes = Path(__file__).with_name("flow_selectors.py").read_bytes()
        control_bytes = Path(__file__).read_bytes()
        return {
            "state_machine": hashlib.sha256(engine_bytes + control_bytes).hexdigest(),
            "milestone": hashlib.sha256(engine_bytes).hexdigest(),
            "flow_selector": hashlib.sha256(selector_bytes).hexdigest(),
        }

    @staticmethod
    def _relative_file(bundle_root: Path, name: str) -> Path:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise TransitionError(f"bundle contract path escapes its owner: {name!r}")
        resolved = (bundle_root / path).resolve()
        try:
            resolved.relative_to(bundle_root.resolve())
        except ValueError as exc:
            raise TransitionError(f"bundle contract path escapes its owner: {name!r}") from exc
        if not resolved.is_file() or resolved.is_symlink():
            raise TransitionError(f"bundle contract file is missing or linked: {name!r}")
        return resolved

    def _bundle_files(self, bundle_root: Path) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for path in sorted(bundle_root.rglob("*")):
            if path.is_symlink():
                raise TransitionError(f"StateWork bundles cannot contain symlinks: {path}")
            if path.is_file():
                hashes[path.relative_to(bundle_root).as_posix()] = hashlib.sha256(
                    path.read_bytes()).hexdigest()
        return hashes

    def _load_fragment(self, bundle_root: Path, relative: Optional[str], *,
                       fragment: str) -> dict[str, Any]:
        if not relative:
            return {}
        path = self._relative_file(bundle_root, relative)
        value = _load_yaml(path) or {}
        if not isinstance(value, Mapping) or not isinstance(value.get(fragment), Mapping):
            raise TransitionError(f"{fragment} contract fragment must be a mapping")
        return dict(value[fragment])

    def compile(self, *, write: bool = False) -> dict[str, Any]:
        registry_path = self.root / "registry.yaml"
        registry = _load_yaml(registry_path) or {}
        if str(registry.get("version")) != self.VERSION:
            raise TransitionError("registry.yaml must declare registry bundle version 2.0.0")
        base_ids = list(registry.get("stateworks") or ())
        if len(base_ids) != len(set(base_ids)):
            raise TransitionError("registry.yaml contains duplicate StateWork IDs")
        roots: list[tuple[str, Path, Optional[list[str]]]] = [(".", self.root, base_ids)]
        for index, raw in enumerate(registry.get("extension_roots") or ()):
            if not isinstance(raw, str) or not raw:
                raise TransitionError("extension_roots must contain trusted root paths")
            target = Path(raw).expanduser()
            target = (self.root / target).resolve() if not target.is_absolute() else target.resolve()
            if not target.is_dir() or target.is_symlink():
                raise TransitionError(f"trusted extension root is unavailable or linked: {raw}")
            roots.append((f"extension:{index}", target, None))

        global_packets = load_packet_registry(self.root / "schemas" / "packet-registry.yaml")
        global_evidence = load_evidence_kind_registry(
            self.root / "schemas" / "evidence-kinds.yaml")
        packet_rows: dict[str, dict[str, Any]] = dict(global_packets.get("packets") or {})
        packet_schema_docs: dict[str, dict[str, Any]] = {}
        for packet_id, meta in packet_rows.items():
            schema_path = self.root / "schemas" / str(meta.get("schema") or "")
            if schema_path.is_file():
                packet_schema_docs[packet_id] = json.loads(schema_path.read_text(encoding="utf-8"))
        evidence_rows: dict[str, dict[str, Any]] = dict(global_evidence.get("kinds") or {})
        compiled: list[dict[str, Any]] = []
        source_by_id: dict[str, tuple[str, Path]] = {}

        for root_ref, source_root, explicit_ids in roots:
            candidates = ([source_root / sid for sid in explicit_ids]
                          if explicit_ids is not None else sorted(
                              path.parent for path in source_root.glob("*/manifest.yaml")))
            for bundle_root in candidates:
                manifest_path = bundle_root / "manifest.yaml"
                if not manifest_path.is_file() or manifest_path.is_symlink():
                    raise TransitionError(f"bundle {bundle_root} is missing a regular manifest.yaml")
                manifest = _load_yaml(manifest_path) or {}
                sid = str(manifest.get("id") or "")
                if not sid or sid != bundle_root.name or sid in source_by_id:
                    raise TransitionError(f"StateWork identifier collision or path mismatch: {sid!r}")
                schema_path = self.root / "schemas" / "statework-manifest.schema.json"
                jsonschema.validate(instance=manifest,
                                    schema=json.loads(schema_path.read_text(encoding="utf-8")))
                if manifest.get("bundle_schema_version") != 2:
                    raise TransitionError(f"StateWork {sid!r} must use bundle schema version 2")
                flow_policy = manifest.get("flow_selection") or {}
                flow_schema_path = self.root / "schemas" / "statework-flow.schema.json"
                flow_schema = json.loads(flow_schema_path.read_text(encoding="utf-8"))
                flow_paths = sorted(bundle_root.glob("flows/*/flow.md"))
                fallbacks = []
                for flow_path in flow_paths:
                    pieces = flow_path.read_text(encoding="utf-8").split("---", 2)
                    if len(pieces) != 3 or pieces[0].strip():
                        raise TransitionError(
                            f"StateWork {sid!r} flow {flow_path.parent.name!r} lacks frontmatter")
                    try:
                        flow_meta = yaml.safe_load(pieces[1]) or {}
                        jsonschema.validate(instance=flow_meta, schema=flow_schema)
                        if flow_meta.get("flow") != flow_path.parent.name:
                            raise TransitionError(
                                f"StateWork {sid!r} flow name differs from its directory")
                        if (flow_meta.get("states")
                                and str((manifest.get("engine") or {}).get("kind") or "")
                                != "state_machine"):
                            raise TransitionError(
                                f"StateWork {sid!r} non-state-machine flows cannot declare states")
                        if "when" in flow_meta:
                            FlowSelector.validate_predicate(flow_meta["when"])
                    except (ValueError, jsonschema.ValidationError, yaml.YAMLError) as exc:
                        raise TransitionError(
                            f"StateWork {sid!r} flow {flow_path.parent.name!r} is invalid: {exc}") from exc
                    if flow_meta.get("fallback") is True:
                        fallbacks.append(flow_path.parent.name)
                fallback_policy = str(flow_policy.get("fallback"))
                if ((fallback_policy == "required" and len(fallbacks) != 1)
                        or (fallback_policy == "optional" and len(fallbacks) > 1)
                        or (fallback_policy == "forbidden" and fallbacks)):
                    raise TransitionError(
                        f"StateWork {sid!r} fallback policy {fallback_policy!r} "
                        f"does not match declared fallback flows {fallbacks}")
                files = self._bundle_files(bundle_root)
                if "manifest.yaml" not in files:
                    raise TransitionError(f"StateWork {sid!r} manifest is not part of its bundle")
                engine_decl = manifest.get("engine") or {}
                kind = str(engine_decl.get("kind") or "")
                contract_relative = str(engine_decl.get("contract") or "")
                contract_path = self._relative_file(bundle_root, contract_relative)
                workflow_contract = _load_yaml(contract_path) or {}
                contracts = manifest.get("contracts") or {}
                local_packets = self._load_fragment(
                    bundle_root, contracts.get("packets"), fragment="packets")
                local_evidence = self._load_fragment(
                    bundle_root, contracts.get("evidence"), fragment="kinds")
                for packet_id, row in local_packets.items():
                    if not isinstance(row, Mapping):
                        raise TransitionError(f"packet fragment {packet_id!r} is malformed")
                    schema_relative = str(row.get("schema") or "")
                    local_schema_path = self._relative_file(bundle_root, schema_relative)
                    schema_doc = json.loads(local_schema_path.read_text(encoding="utf-8"))
                    jsonschema.Draft202012Validator.check_schema(schema_doc)
                    existing = packet_rows.get(str(packet_id))
                    if existing is not None:
                        previous_schema = packet_schema_docs.get(str(packet_id))
                        if ({key: value for key, value in existing.items() if key != "schema"}
                                != {key: value for key, value in row.items() if key != "schema"}
                                or previous_schema is not None and previous_schema != schema_doc):
                            raise TransitionError(f"packet contract collision for {packet_id!r}")
                    packet_rows[str(packet_id)] = dict(row)
                    packet_schema_docs[str(packet_id)] = schema_doc
                for kind_id, row in local_evidence.items():
                    if not isinstance(row, Mapping):
                        raise TransitionError(f"evidence declaration {kind_id!r} is malformed")
                    existing = evidence_rows.get(str(kind_id))
                    if existing is not None and dict(existing) != dict(row):
                        raise TransitionError(f"evidence kind collision for {kind_id!r}")
                    evidence_rows[str(kind_id)] = dict(row)

                if kind == "state_machine":
                    evidence_registry = {"kinds": evidence_rows}
                    engine_impl: Any = StateMachineWorkflowEngine(TransitionEngine(
                        dict(workflow_contract), evidence_registry=evidence_registry,
                        require_registered=True))
                elif kind == "milestone":
                    engine_impl = MilestoneWorkflowEngine()
                else:
                    engine_impl = self.engine_registry.get(kind)
                engine_impl.validate_contract(workflow_contract)
                contract_digest = self._digest(workflow_contract)

                ref = (bundle_root.relative_to(source_root).as_posix()
                       if bundle_root != source_root else ".")
                try:
                    source_root_ref = source_root.relative_to(self.root).as_posix()
                except ValueError:
                    source_root_ref = str(source_root)
                if source_root == self.root:
                    source_root_ref = "."
                files_digest = self._digest(files)
                guidance_path = bundle_root / "guidance.md"
                guidance = (guidance_path.read_text(encoding="utf-8")
                            if guidance_path.is_file() and not guidance_path.is_symlink()
                            else "")
                runtime_capsule = render_runtime_capsule(
                    manifest, engine_kind=kind,
                    contract_version=str(engine_decl.get("contract_version") or ""),
                    flows=(path.parent.name for path in flow_paths),
                    guidance=guidance)
                source_by_id[sid] = (root_ref, source_root)
                compiled.append({
                    "id": sid, "root_ref": root_ref,
                    "source_root": source_root_ref,
                    "bundle_ref": ref, "bundle_hash": files_digest,
                    "file_hashes": files, "manifest": dict(manifest),
                    "engine": {"kind": kind,
                               "contract_version": str(engine_decl.get("contract_version") or ""),
                               "contract_path": contract_relative,
                               "contract_hash": contract_digest,
                               "contract": dict(workflow_contract)},
                    "runtime_capsule": runtime_capsule,
                    "runtime_capsule_hash": hashlib.sha256(
                        runtime_capsule.encode("utf-8")).hexdigest(),
                    "contracts": {"packets": list(local_packets),
                                  "evidence": list(local_evidence)}})

        by_id = {item["id"]: item for item in compiled}
        for item in compiled:
            composition = item["manifest"].get("composition") or {}
            missing = set(composition.get("requires") or ()) - set(by_id)
            if missing:
                raise TransitionError(f"StateWork {item['id']!r} requires missing bundles: {sorted(missing)}")
            unknown_conflicts = set(composition.get("conflicts") or ()) - set(by_id)
            if unknown_conflicts:
                raise TransitionError(f"StateWork {item['id']!r} names missing conflicts: {sorted(unknown_conflicts)}")
        for packet_id, meta in packet_rows.items():
            producer = str(meta.get("producer") or "")
            if producer and producer not in by_id:
                raise TransitionError(
                    f"packet {packet_id!r} names unavailable producer {producer!r}")

        body = {"registry_version": self.VERSION,
                "registry_config_hash": hashlib.sha256(registry_path.read_bytes()).hexdigest(),
                "stateworks": compiled,
                "packet_registry": {"version": "2.0.0", "packets": packet_rows},
                "packet_schemas": packet_schema_docs,
                "evidence_registry": {"version": str(global_evidence.get("version") or "1.0.0"),
                                      "kinds": evidence_rows},
                "freshness_validator_hashes": dict(FRESHNESS_VALIDATORS.identities),
                "builtin_engine_hashes": self._builtin_engine_hashes(),
                "workflow_engine_hashes": dict(self.engine_registry.identities)}
        result = {**body, "registry_hash": self._digest(body)}
        if write:
            path = self.root / "compiled-registry.json"
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                                 encoding="utf-8")
            os.replace(temporary, path)
        return result


def load_compiled_registry(root: Optional[Path] = None, *,
                           verify_bundles: bool = True) -> dict[str, Any]:
    """Load the immutable compile artifact and verify its complete source hashes."""
    root = Path(root or ROOT).resolve()
    path = root / "compiled-registry.json"
    if not path.is_file() or path.is_symlink():
        raise TransitionError("compiled-registry.json is required; run compile-registry.py")
    result = json.loads(path.read_text(encoding="utf-8"))
    body = {key: value for key, value in result.items() if key != "registry_hash"}
    if result.get("registry_hash") != RegistryCompiler._digest(body):
        raise TransitionError("compiled registry content hash is invalid")
    if result.get("registry_version") != RegistryCompiler.VERSION:
        raise TransitionError("compiled registry version is unsupported")
    if result.get("freshness_validator_hashes") != dict(FRESHNESS_VALIDATORS.identities):
        raise TransitionError("compiled freshness-validator registry changed")
    if result.get("builtin_engine_hashes") != RegistryCompiler._builtin_engine_hashes():
        raise TransitionError("compiled workflow engine implementation changed")
    for item in result.get("stateworks") or ():
        capsule = str(item.get("runtime_capsule") or "")
        capsule_hash = hashlib.sha256(capsule.encode("utf-8")).hexdigest()
        if capsule_hash != item.get("runtime_capsule_hash"):
            raise TransitionError(
                f"compiled runtime capsule for {item.get('id')!r} has an invalid hash")
        source_root_ref = str(item.get("source_root") or ".")
        source_root = (root if source_root_ref == "." else
                       Path(source_root_ref) if Path(source_root_ref).is_absolute()
                       else root / source_root_ref)
        bundle_root = (source_root / str(item.get("bundle_ref") or ".")).resolve()
        if verify_bundles:
            actual: dict[str, str] = {}
            for rel, expected in dict(item.get("file_hashes") or {}).items():
                file_path = RegistryCompiler._relative_file(bundle_root, rel)
                actual[rel] = hashlib.sha256(file_path.read_bytes()).hexdigest()
                if actual[rel] != expected:
                    raise TransitionError(f"compiled StateWork {item.get('id')!r} changed: {rel}")
            if RegistryCompiler._digest(actual) != item.get("bundle_hash"):
                raise TransitionError(f"compiled StateWork {item.get('id')!r} bundle hash changed")
        item["bundle_root"] = str(bundle_root)
    return result


class StandaloneHostInterface:
    """Small host facade for enforcing installations."""
    def __init__(self, *, root: Path, state_path: Optional[Path] = None,
                 evidence_path: Optional[Path] = None) -> None:
        self.root = Path(root)
        self.evidence_path = Path(evidence_path) if evidence_path else self.root / "state" / "evidence.json"
        self.state_store = SubjectStateStore(Path(state_path) if state_path else self.root / "state" / "subjects.json")
        self.evidence_store = EvidenceStore()
        self.packet_store = PacketStore(
            packet_registry_path=self.root / "schemas" / "packet-registry.yaml",
            storage_path=self.root / "state" / "packets.json")
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
        if not isinstance(record, Mapping):
            raise TransitionError("observation must be a mapping")
        candidate = dict(record)
        kind = candidate.get("kind")
        registry = load_evidence_kind_registry(self.root / "schemas" / "evidence-kinds.yaml")
        spec = (registry.get("kinds") or {}).get(kind)
        if spec:
            if not spec.get("mintable_by_host"):
                raise TransitionError(
                    f"evidence kind {kind!r} requires its registered specialized issuer")
            if len(spec.get("allowed_issuers") or []) != 1:
                raise TransitionError(f"host-minted evidence kind {kind!r} has ambiguous issuers")
            metadata = {
                "issuer": spec["allowed_issuers"][0],
                "validator": spec["validator"],
                "schema": spec["schema"],
            }
            for key, value in metadata.items():
                if key in candidate and candidate[key] != value:
                    raise TransitionError(f"caller cannot declare trusted evidence field {key!r}")
                candidate[key] = value
            if not isinstance(candidate.get("subject_ref"), str) or not candidate["subject_ref"]:
                raise TransitionError("registered evidence requires subject_ref")
            _aware_datetime(candidate.get("observed_at"))
            digest = candidate.get("content_digest")
            if not isinstance(digest, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
                raise TransitionError(
                    "registered evidence requires a SHA-256 content_digest from the host observation")
        ref = self.evidence_store.create(candidate)
        self.evidence_store.save(self.evidence_path)
        return ref

    def publish_packet(self, packet: Mapping[str, Any], *, storage_path: Optional[Path] = None) -> str:
        """Publish a validated handoff packet through CSW's typed store."""
        if not isinstance(packet, Mapping):
            raise TransitionError("handoff packet must be a mapping")
        if storage_path is not None:
            store = PacketStore(
                packet_registry_path=self.root / "schemas" / "packet-registry.yaml",
                storage_path=storage_path)
        else:
            store = self.packet_store
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
