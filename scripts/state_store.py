"""Durable state and packet stores for CognitiveStateWork."""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import jsonschema
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
import yaml

if __package__:
    from .errors import PacketValidationError, TransitionError
    from .resources import (ROOT, _load_yaml, _local_schema_registry,
                            _package_resource, _schema_text)
    from .evidence import evaluate_freshness
else:
    from errors import PacketValidationError, TransitionError
    from resources import (ROOT, _load_yaml, _local_schema_registry,
                           _package_resource, _schema_text)
    from evidence import evaluate_freshness

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
