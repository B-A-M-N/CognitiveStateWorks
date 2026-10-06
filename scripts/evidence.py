"""Trusted evidence validators, freshness evaluation, and attested storage."""
from __future__ import annotations

import fcntl
import hashlib
import inspect
import json
from importlib import metadata
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

if __package__:
    from .errors import TransitionError
    from .resources import ROOT, _aware_datetime
    from .repository_truth import validate_repository_truth_packet
    from .workflow_engines import EngineRegistry
else:
    from errors import TransitionError
    from resources import ROOT, _aware_datetime
    from repository_truth import validate_repository_truth_packet
    from workflow_engines import EngineRegistry


def _repository_truth_v1(packet: Dict[str, Any], context: Mapping[str, Any]) -> bool:
    """Trusted repository-currentness validator selected by the registry."""
    repo_path = context.get("repository_path")
    if repo_path:
        return bool(validate_repository_truth_packet(
            packet, Path(repo_path)).get("valid"))
    expected_vector = context.get("repository_freshness")
    actual_vector = packet.get("payload", {}).get("freshness", {})
    required = ("repo_identity", "observed_head", "working_tree_fingerprint",
                "active_worktree_snapshot", "remote_state_fingerprint")
    if not isinstance(expected_vector, Mapping):
        return False
    return all(key in expected_vector and expected_vector.get(key) == actual_vector.get(key)
               for key in required)


class TrustedValidatorRegistry:
    """Host-trusted callable registry loaded only from explicit source pins."""
    def __init__(self, entry_point_group: str) -> None:
        if not isinstance(entry_point_group, str) or not entry_point_group.strip():
            raise ValueError("validator registry requires an entry-point group")
        self._validators: Dict[str, Any] = {}
        self._hashes: Dict[str, str] = {}
        self.entry_point_group = entry_point_group

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

    def contains(self, validator_id: str) -> bool:
        return validator_id in self._validators

    @staticmethod
    def _entry_point_identity(entry_point: Any) -> str:
        return EngineRegistry.entry_point_identity(entry_point)

    @staticmethod
    def _entry_point_source_hash(entry_point: Any) -> str:
        return EngineRegistry.entry_point_source_hash(entry_point)

    def _load_entries(self, trusted_entry_points: Mapping[str, str],
                      entry_points: Iterable[Any]) -> tuple[str, ...]:
        """Load only validator source trees explicitly adopted by the host."""
        if not isinstance(trusted_entry_points, Mapping):
            raise TypeError("trusted validator entry points must be a host-owned mapping")
        if not trusted_entry_points:
            return ()
        discovered: Dict[str, Any] = {}
        for entry_point in entry_points:
            try:
                identity = self._entry_point_identity(entry_point)
            except (AttributeError, TypeError, ValueError):
                continue
            if identity not in trusted_entry_points:
                continue
            if identity in discovered:
                raise ValueError(f"duplicate trusted validator entry point {identity!r}")
            discovered[identity] = entry_point
        missing = set(trusted_entry_points) - set(discovered)
        if missing:
            raise ValueError(f"trusted validator entry points are unavailable: {sorted(missing)}")

        loaded: List[str] = []
        for identity, expected_hash in trusted_entry_points.items():
            if (not isinstance(expected_hash, str) or len(expected_hash) != 64
                    or any(char not in "0123456789abcdef" for char in expected_hash)):
                raise ValueError("trusted validator pins must be lowercase SHA-256 hashes")
            entry_point = discovered[identity]
            actual_hash = self._entry_point_source_hash(entry_point)
            if actual_hash != expected_hash:
                raise PermissionError(
                    f"validator entry point source differs from host trust pin: {identity}")
            implementation = entry_point.load()
            if not callable(implementation):
                raise TypeError("validator entry point must load a callable")
            self.register(entry_point.name, implementation,
                          implementation_hash=actual_hash, trusted=True)
            loaded.append(entry_point.name)
        return tuple(loaded)

    def load_trusted_entry_points(self, trusted_entry_points: Mapping[str, str]
                                  ) -> tuple[str, ...]:
        """Load the host's configured validator entry points after checking pins."""
        if not trusted_entry_points:
            return ()
        entries = metadata.entry_points(group=self.entry_point_group)
        return self._load_entries(trusted_entry_points, entries)

    def validate(self, validator_id: str, packet: Dict[str, Any],
                 context: Mapping[str, Any]) -> bool:
        implementation = self._validators.get(validator_id)
        return bool(implementation and implementation(packet, context))

    @property
    def identities(self) -> Mapping[str, str]:
        return dict(self._hashes)


def _trusted_validator_hash(function: Any) -> str:
    return hashlib.sha256(inspect.getsource(function).encode("utf-8")).hexdigest()


class FreshnessValidatorRegistry(TrustedValidatorRegistry):
    def __init__(self) -> None:
        super().__init__("cognitive_statework.freshness_validators")


class EvidenceValidatorRegistry(TrustedValidatorRegistry):
    def __init__(self) -> None:
        super().__init__("cognitive_statework.evidence_validators")


FRESHNESS_VALIDATORS = FreshnessValidatorRegistry()
FRESHNESS_VALIDATORS.register(
    "repository_truth_v1", _repository_truth_v1,
    implementation_hash=_trusted_validator_hash(_repository_truth_v1), trusted=True)
EVIDENCE_VALIDATORS = EvidenceValidatorRegistry()


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
    def __init__(self, records: Optional[Iterable[Mapping[str, Any]]] = (), *,
                 validator_registry: Optional[TrustedValidatorRegistry] = None) -> None:
        self._records: Dict[str, Dict[str, Any]] = {}
        self.validator_registry = validator_registry or EVIDENCE_VALIDATORS
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
        validator_id = str(candidate.get("validator") or "")
        if (validator_id and self.validator_registry.contains(validator_id)
                and not self.validator_registry.validate(validator_id, candidate, {})):
            raise TransitionError(
                f"registered evidence validator {validator_id!r} rejected the record")
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

    def refresh_attested(self, path: Path) -> None:
        """Reload the current durable evidence revision under the store lock.

        Independent WorkflowAuthority instances may share this evidence file.
        Reconciliation must evaluate the same current evidence regardless of
        which instance originally accepted the transition.
        """
        path = Path(path)
        if not path.exists():
            self._records = {}
            return
        lock_path = path.with_name(path.name + ".lock")
        try:
            with lock_path.open("a+", encoding="utf-8") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
                records = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(records, list):
                    raise TransitionError("trusted evidence store is malformed")
                loaded = type(self).load_attested(records)
        except (OSError, json.JSONDecodeError) as exc:
            raise TransitionError("trusted evidence store is unreadable") from exc
        self._records = loaded._records

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
