"""Atomic persistence for authorized StateWork selections."""
from __future__ import annotations

import copy
import fcntl
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

if __package__:
    from .errors import TransitionError
else:
    from errors import TransitionError

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
