#!/usr/bin/env python3
"""Validated packet and transition primitives for CognitiveStateWork."""
from __future__ import annotations

import json
import copy
import fcntl
import hashlib
import inspect
from importlib import metadata
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
if __package__:
    from .workflow_engines import (EngineRegistry, MilestoneWorkflowEngine,
                                   StateMachineWorkflowEngine, WorkflowDecision,
                                   WorkflowIdentity, WorkflowProgressFact,
                                   WorkflowSnapshot)
    from .flow_selectors import FlowSelector
else:
    from workflow_engines import (EngineRegistry, MilestoneWorkflowEngine,
                                  StateMachineWorkflowEngine, WorkflowDecision,
                                  WorkflowIdentity, WorkflowProgressFact,
                                  WorkflowSnapshot)
    from flow_selectors import FlowSelector

if __package__:
    from .errors import PacketValidationError, TransitionError
    from .resources import (EVIDENCE_KIND_REGISTRY_PATH, ROOT, _aware_datetime,
                            _CHECKOUT_ROOT, _CODE_ROOT, _PACKAGED_BUILTIN_ROOT,
                            _load_yaml, _local_schema_registry, _package_resource,
                            _schema_resource, _schema_text, load_evidence_kind_registry,
                            load_packet_registry, render_runtime_capsule)
    from .evidence import (EVIDENCE_VALIDATORS, FRESHNESS_VALIDATORS,
                           EvidenceStore, EvidenceValidatorRegistry,
                           FreshnessValidatorRegistry, TrustedValidatorRegistry,
                           _path_value, _repository_truth_v1,
                           _trusted_validator_hash, evaluate_freshness)
else:
    from errors import PacketValidationError, TransitionError
    from resources import (EVIDENCE_KIND_REGISTRY_PATH, ROOT, _aware_datetime,
                           _CHECKOUT_ROOT, _CODE_ROOT, _PACKAGED_BUILTIN_ROOT,
                           _load_yaml, _local_schema_registry, _package_resource,
                           _schema_resource, _schema_text, load_evidence_kind_registry,
                           load_packet_registry, render_runtime_capsule)
    from evidence import (EVIDENCE_VALIDATORS, FRESHNESS_VALIDATORS,
                          EvidenceStore, EvidenceValidatorRegistry,
                          FreshnessValidatorRegistry, TrustedValidatorRegistry,
                          _path_value, _repository_truth_v1,
                          _trusted_validator_hash, evaluate_freshness)

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


class WorkflowSelectionStore:
    """Revisioned CSW-owned active workflow sets scoped to one task subject."""

    SCOPE_FIELDS = ("namespace_id", "application_id", "application_instance_id",
                    "workflow_id", "subject_ref")

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)

    @classmethod
    def _scope_key(cls, scope: Mapping[str, Any]) -> str:
        if not isinstance(scope, Mapping) or set(scope) != set(cls.SCOPE_FIELDS):
            raise TransitionError("workflow selection scope has missing or unknown fields")
        normalized = {}
        for name in cls.SCOPE_FIELDS:
            value = scope.get(name)
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise TransitionError(f"workflow selection scope {name} is invalid")
            normalized[name] = value
        return json.dumps(normalized, sort_keys=True, separators=(",", ":"))

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 2, "scopes": {}}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TransitionError("workflow selection store is unreadable") from exc
        if (not isinstance(value, dict) or value.get("version") not in {1, 2}
                or not isinstance(value.get("scopes"), dict)):
            raise TransitionError("workflow selection store has invalid structure")
        # Older selections were host-owned and permanent. Preserve that
        # authority when reading them after the lease-aware format is deployed.
        if value["version"] == 1:
            for selection in value["scopes"].values():
                if not isinstance(selection, dict):
                    raise TransitionError("workflow selection record has invalid structure")
                revision = int(selection.get("revision", 0))
                active = selection.get("active_workflows")
                if not isinstance(active, dict):
                    raise TransitionError("workflow selection record has invalid structure")
                for statework_id, row in tuple(active.items()):
                    if not isinstance(row, dict) or set(row) != {"identity", "contract_hash"}:
                        raise TransitionError("legacy active workflow row is malformed")
                    active[statework_id] = {
                        **row, "activation_owner": "host",
                        "control_session_id": None, "intervention_id": None,
                        "activation_revision": revision, "expires_at_action": None,
                    }
            value["version"] = 2
        return value

    def get(self, scope: Mapping[str, Any]) -> dict[str, Any]:
        key = self._scope_key(scope)
        self.lock_path.touch(mode=0o600, exist_ok=True)
        with self.lock_path.open("r", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
            record = self._read_unlocked()["scopes"].get(key) or {
                "scope": {name: scope[name] for name in self.SCOPE_FIELDS},
                "revision": 0, "active_workflows": {},
            }
            if (not isinstance(record, dict)
                    or not isinstance(record.get("active_workflows"), dict)
                    or not isinstance(record.get("revision"), int)):
                raise TransitionError("workflow selection record has invalid structure")
            return copy.deepcopy(record)

    def replace(self, scope: Mapping[str, Any], *, expected_revision: int,
                active_workflows: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        key = self._scope_key(scope)
        if not isinstance(active_workflows, Mapping) or len(active_workflows) > 16:
            raise TransitionError("active workflow set exceeds its bounds")
        candidate = copy.deepcopy(dict(active_workflows))
        if any(not isinstance(statework_id, str) or not statework_id
               or not isinstance(row, Mapping)
               or set(row) != {"identity", "contract_hash", "activation_owner",
                               "control_session_id", "intervention_id",
                               "activation_revision", "expires_at_action"}
               for statework_id, row in candidate.items()):
            raise TransitionError("active workflow set is malformed")
        for row in candidate.values():
            self._validate_activation_row(row, max_revision=expected_revision + 1)
        self.lock_path.touch(mode=0o600, exist_ok=True)
        with self.lock_path.open("r+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            data = self._read_unlocked()
            prior = data["scopes"].get(key) or {
                "scope": {name: scope[name] for name in self.SCOPE_FIELDS},
                "revision": 0, "active_workflows": {},
            }
            if int(prior.get("revision", 0)) != int(expected_revision):
                raise TransitionError(
                    f"workflow selection revision conflict: expected {expected_revision}, "
                    f"found {prior.get('revision', 0)}; re-inspect required")
            updated = {"scope": {name: scope[name] for name in self.SCOPE_FIELDS},
                       "revision": int(expected_revision) + 1,
                       "active_workflows": candidate}
            data["scopes"][key] = updated
            data["version"] = 2
            fd, temporary = tempfile.mkstemp(dir=str(self.path.parent),
                                             prefix=f".{self.path.name}.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(data, stream, sort_keys=True, separators=(",", ":"))
                    stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
                os.chmod(temporary, 0o600)
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return copy.deepcopy(updated)

    @staticmethod
    def _validate_activation_row(row: Mapping[str, Any], *, max_revision: int) -> None:
        owner = row.get("activation_owner")
        if owner not in {"host", "digitalpsychology"}:
            raise TransitionError("workflow activation owner is invalid")
        control_session_id = row.get("control_session_id")
        intervention_id = row.get("intervention_id")
        expiry = row.get("expires_at_action")
        activation_revision = row.get("activation_revision")
        if (type(activation_revision) is not int or activation_revision < 0
                or activation_revision > max_revision):
            raise TransitionError("workflow activation revision is invalid")
        if owner == "host":
            if control_session_id is not None or intervention_id is not None or expiry is not None:
                raise TransitionError("host activation cannot carry a DP lease")
        elif (not isinstance(control_session_id, str) or not control_session_id
              or len(control_session_id) > 256
              or not isinstance(intervention_id, str) or not intervention_id
              or len(intervention_id) > 128
              or type(expiry) is not int or expiry < 0):
            raise TransitionError("DigitalPsychology workflow lease is malformed")


class WorkflowAuthority:
    """Generic host authority over compiled StateWork workflow engines.

    Engine choice and step semantics stay inside CSW. Consumers inspect a
    normalized snapshot and submit an engine-neutral step identifier.
    """
    def __init__(self, *, root: Optional[Path] = None,
                 state_store: Optional[SubjectStateStore] = None,
                 evidence_store: Optional[EvidenceStore] = None,
                 engine_registry: Optional[EngineRegistry] = None,
                 selection_store: Optional[WorkflowSelectionStore] = None):
        self.root = Path(root or ROOT)
        self.state_store = state_store or SubjectStateStore(
            self.root / "state" / "subjects.json")
        self.evidence_store = evidence_store or EvidenceStore()
        self.engine_registry = engine_registry or EngineRegistry()
        self.selection_store = selection_store or WorkflowSelectionStore(
            self.root / "state" / "workflow-selections.json")
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
            expected_engine_hash = dict(compiled.get("workflow_engine_hashes") or {}).get(kind)
            registered_engine_hash = self.engine_registry.identities.get(kind)
            if (expected_engine_hash is None
                    or registered_engine_hash != expected_engine_hash):
                raise TransitionError(
                    f"workflow engine {kind!r} differs from the compiled host trust pin")
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

    @staticmethod
    def _selection_scope(identity: WorkflowIdentity | Mapping[str, Any]
                         ) -> dict[str, str]:
        identity = WorkflowAuthority._identity(identity)
        return {name: str(getattr(identity, name))
                for name in WorkflowSelectionStore.SCOPE_FIELDS}

    @staticmethod
    def _depends_on(entries: Mapping[str, Mapping[str, Any]],
                    statework_id: str, target_id: str) -> bool:
        pending = [statework_id]
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            manifest = dict(entries[current].get("manifest") or {})
            required_ids = set((manifest.get("composition") or {}).get("requires") or ())
            if target_id in required_ids:
                return True
            pending.extend(item for item in required_ids if item in entries)
        return False

    @classmethod
    def _selection_compatible(cls, entries: Mapping[str, Mapping[str, Any]],
                              statework_id: str, active_ids: set[str]) -> bool:
        manifest = dict(entries[statework_id].get("manifest") or {})
        composition = dict(manifest.get("composition") or {})
        if not set(composition.get("requires") or ()).issubset(active_ids):
            return False
        if set(composition.get("conflicts") or ()).intersection(active_ids):
            return False
        group = str(composition.get("group") or "")
        for active_id in active_ids:
            active_manifest = dict(entries[active_id].get("manifest") or {})
            active_composition = dict(active_manifest.get("composition") or {})
            active_group = str(active_composition.get("group") or "")
            if (group and group == active_group
                    and not cls._depends_on(entries, statework_id, active_id)
                    and not cls._depends_on(entries, active_id, statework_id)):
                return False
        return True

    def activate_workflow(self, identity: WorkflowIdentity | Mapping[str, Any], *,
                          contract_hash: str,
                          expected_selection_revision: int,
                          activation_owner: str = "host",
                          control_session_id: Optional[str] = None,
                          intervention_id: Optional[str] = None,
                          expires_at_action: Optional[int] = None) -> dict[str, Any]:
        """Activate a StateWork only after CSW checks registration and composition."""
        lease = {
            "activation_owner": activation_owner,
            "control_session_id": control_session_id,
            "intervention_id": intervention_id,
            "expires_at_action": expires_at_action,
        }
        WorkflowSelectionStore._validate_activation_row(
            {**lease, "identity": {}, "contract_hash": contract_hash,
             "activation_revision": expected_selection_revision + 1},
            max_revision=expected_selection_revision + 1)
        identity = self._identity(identity)
        statework_id = identity.statework_id
        manifest, _contract, digest, engine, _evidence = self._bundle(
            statework_id, contract_hash)
        if digest != contract_hash:
            raise TransitionError("workflow contract pin is not current")
        scope = self._selection_scope(identity)
        selection = self.selection_store.get(scope)
        if int(selection["revision"]) != int(expected_selection_revision):
            raise TransitionError(
                f"workflow selection revision conflict: expected {expected_selection_revision}, "
                f"found {selection['revision']}; re-inspect required")
        active = dict(selection["active_workflows"])
        if statework_id in active:
            row = active[statework_id]
            if (row.get("identity") != dict(identity.__dict__)
                    or row.get("contract_hash") != digest
                    or any(row.get(key) != value for key, value in lease.items())):
                raise TransitionError(
                    "active workflow identity or lease differs from the current request")
            return selection
        if len(active) >= 16:
            raise TransitionError("active workflow set exceeds its bounds")
        compiled = load_compiled_registry(self.root)
        entries = {str(item.get("id")): item for item in compiled.get("stateworks") or ()}
        if not self._selection_compatible(entries, statework_id, set(active)):
            raise TransitionError("StateWork is not composition-compatible with the active set")
        # Initialize through the same authoritative engine before publishing
        # the active selection. An interrupted activation can leave an
        # initialized but inactive subject, never an active uninitialized one.
        self.inspect_workflow(identity, contract_hash=digest)
        active[statework_id] = {
            "identity": dict(identity.__dict__), "contract_hash": digest,
            **lease, "activation_revision": expected_selection_revision + 1,
        }
        return self.selection_store.replace(
            scope, expected_revision=expected_selection_revision,
            active_workflows=active)

    def deactivate_workflow(self, *, workflow_scope: Mapping[str, Any],
                            statework_id: str,
                            expected_selection_revision: int,
                            expected_activation_owner: Optional[str] = None,
                            expected_control_session_id: Optional[str] = None,
                            expected_intervention_id: Optional[str] = None) -> dict[str, Any]:
        """Remove an active workflow unless another active workflow requires it."""
        if (expected_activation_owner == "digitalpsychology"
                and (not expected_control_session_id or not expected_intervention_id)):
            raise TransitionError(
                "DigitalPsychology release requires its control session and intervention ID")
        selection = self.selection_store.get(workflow_scope)
        if int(selection["revision"]) != int(expected_selection_revision):
            raise TransitionError(
                f"workflow selection revision conflict: expected {expected_selection_revision}, "
                f"found {selection['revision']}; re-inspect required")
        active = dict(selection["active_workflows"])
        if statework_id not in active:
            raise TransitionError(f"StateWork {statework_id!r} is not active")
        row = active[statework_id]
        for name, expected in (
                ("activation_owner", expected_activation_owner),
                ("control_session_id", expected_control_session_id),
                ("intervention_id", expected_intervention_id)):
            if expected is not None and row.get(name) != expected:
                raise TransitionError(
                    f"StateWork {statework_id!r} activation {name} does not match")
        compiled = load_compiled_registry(self.root)
        entries = {str(item.get("id")): item for item in compiled.get("stateworks") or ()}
        for other_id in set(active) - {statework_id}:
            if self._depends_on(entries, other_id, statework_id):
                raise TransitionError(
                    f"StateWork {statework_id!r} is required by active {other_id!r}")
        active.pop(statework_id)
        return self.selection_store.replace(
            workflow_scope, expected_revision=expected_selection_revision,
            active_workflows=active)

    def workflow_activation_metadata(self, *, workflow_scope: Mapping[str, Any],
                                     statework_id: str) -> Optional[dict[str, Any]]:
        """Return CSW-recorded activation ownership for host reconciliation."""
        selection = self.selection_store.get(workflow_scope)
        row = selection["active_workflows"].get(statework_id)
        if row is None:
            return None
        WorkflowSelectionStore._validate_activation_row(
            row, max_revision=int(selection["revision"]))
        return {name: row[name] for name in (
            "activation_owner", "control_session_id", "intervention_id",
            "activation_revision", "expires_at_action")}

    def behavioral_snapshot(
            self, *, workflow_scope: Mapping[str, Any],
            candidate_statework_ids: Optional[Iterable[str]] = None,
            host_action_index: Optional[int] = None,
            ) -> dict[str, Any]:
        """Return bounded state and legal choices from CSW-owned workflow selection.

        DigitalPsychology may rank the eligible candidates. Only CSW activates
        or deactivates them and applies their legal, evidence-bound transitions.
        """
        selection = self.selection_store.get(workflow_scope)
        candidates = (list(candidate_statework_ids) if candidate_statework_ids is not None
                      else None)
        if candidates is not None and len(candidates) > 32:
            raise TransitionError("behavioral snapshot request exceeds its bounds")

        compiled = load_compiled_registry(self.root)
        entries = {str(item.get("id")): item
                   for item in compiled.get("stateworks") or ()}
        if host_action_index is not None:
            if type(host_action_index) is not int or host_action_index < 0:
                raise TransitionError("host action index must be non-negative")
            selection = self._expire_workflow_leases(
                workflow_scope, selection, entries, host_action_index)
        active_rows = selection["active_workflows"]
        if len(active_rows) > 16:
            raise TransitionError("active workflow set exceeds its bounds")
        active_ids: set[str] = set()
        active: list[dict[str, Any]] = []
        scope_key = WorkflowSelectionStore._scope_key(workflow_scope)
        expected_scope = json.loads(scope_key)
        for statework_id, row in sorted(active_rows.items()):
            expected_fields = {"identity", "contract_hash", "activation_owner",
                               "control_session_id", "intervention_id",
                               "activation_revision", "expires_at_action"}
            if not isinstance(row, Mapping) or set(row) != expected_fields:
                raise TransitionError("stored active workflow row is malformed")
            WorkflowSelectionStore._validate_activation_row(
                row, max_revision=int(selection["revision"]))
            raw_identity = row.get("identity")
            contract_hash = row.get("contract_hash")
            if not isinstance(raw_identity, Mapping):
                raise TransitionError("stored active workflow identity is malformed")
            identity_fields = {
                "namespace_id", "application_id", "application_instance_id",
                "workflow_id", "subject_ref", "statework_id", "contract_version",
            }
            if set(raw_identity) != identity_fields:
                raise TransitionError("stored active workflow identity is malformed")
            identity = self._identity(raw_identity)
            actual_scope = self._selection_scope(identity)
            if actual_scope != expected_scope or identity.statework_id != statework_id:
                raise TransitionError("stored active workflow escapes its selection scope")
            if statework_id not in entries:
                raise TransitionError(f"active StateWork {statework_id!r} is unavailable")
            snapshot = self.inspect_workflow(identity, contract_hash=str(contract_hash))
            active_ids.add(statework_id)
            active.append({
                "identity": dict(identity.__dict__),
                "contract_hash": str(contract_hash),
                "engine_kind": snapshot.engine_kind,
                "revision": snapshot.revision,
                "current_state": snapshot.current_state,
                "completed": snapshot.completed,
                "eligible_steps": [
                    {"step_id": step.step_id, "label": step.label,
                     "work_class": step.work_class, "domain_effect": step.domain_effect,
                     "required_evidence": list(step.required_evidence),
                     "dependencies": list(step.dependencies)}
                    for step in snapshot.eligible_steps
                ],
            })

        candidates = list(entries) if candidates is None else candidates
        if any(not isinstance(item, str) or not item or len(item) > 128
               for item in candidates):
            raise TransitionError("candidate StateWork IDs must be bounded text")
        if len(candidates) != len(set(candidates)):
            raise TransitionError("candidate StateWork IDs must be unique")
        unknown = sorted(set(candidates) - set(entries))
        if unknown:
            raise TransitionError(f"unavailable candidate StateWorks: {unknown}")
        eligible = []
        for statework_id in sorted(candidates):
            if statework_id in active_ids or not self._selection_compatible(
                    entries, statework_id, active_ids):
                continue
            manifest = dict(entries[statework_id].get("manifest") or {})
            eligible.append({
                "statework_id": statework_id,
                "domain": str(manifest.get("domain") or ""),
                "purpose": str(manifest.get("purpose") or ""),
                "behavior_tags": list(manifest.get("behavior_tags") or ()),
            })

        body = {"registry_hash": compiled["registry_hash"],
                "selection_revision": int(selection["revision"]),
                "active_workflows": active,
                "eligible_stateworks": eligible}
        snapshot_id = hashlib.sha256(json.dumps(
            body, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")).hexdigest()
        return {"snapshot_id": snapshot_id, **body}

    def _expire_workflow_leases(self, workflow_scope: Mapping[str, Any],
                                selection: Mapping[str, Any],
                                entries: Mapping[str, Mapping[str, Any]],
                                host_action_index: int) -> dict[str, Any]:
        """Release expired DP leases while retaining independently owned workflows."""
        active = dict(selection["active_workflows"])
        expired = {
            statework_id for statework_id, row in active.items()
            if row.get("activation_owner") == "digitalpsychology"
            and row.get("expires_at_action") is not None
            and int(row["expires_at_action"]) <= host_action_index
        }
        removed = False
        # Remove expired leaves first, then their now-unneeded dependencies.
        # If a non-expired workflow still depends on an expired lease, retain
        # that lease until the dependent can be released without breaking the
        # selected composition.
        while expired:
            releasable = [statework_id for statework_id in expired
                          if not any(
                              other_id != statework_id
                              and self._depends_on(entries, other_id, statework_id)
                              for other_id in active)]
            if not releasable:
                break
            for statework_id in releasable:
                active.pop(statework_id, None)
                expired.discard(statework_id)
                removed = True
        if not removed:
            return dict(selection)
        return self.selection_store.replace(
            workflow_scope, expected_revision=int(selection["revision"]),
            active_workflows=active)

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


def load_compiled_registry(root: Optional[Path] = None, *,
                           verify_bundles: bool = True) -> Dict[str, Any]:
    """Load the compiled registry through the dedicated registry module."""
    if __package__:
        from .registry import load_compiled_registry as implementation
    else:
        from registry import load_compiled_registry as implementation
    return implementation(root, verify_bundles=verify_bundles)


def __getattr__(name: str) -> Any:
    if name == "RegistryCompiler":
        if __package__:
            from .registry import RegistryCompiler
        else:
            from registry import RegistryCompiler
        return RegistryCompiler
    raise AttributeError(name)


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
