"""Atomic persistence for authorized StateWork selections."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
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
    MAX_TRANSITION_AUDIT_ROWS = 512

    def __init__(self, path: Path) -> None:
        source = Path(path)
        self.legacy_path = source if source.suffix.lower() == ".json" else None
        self.path = source.with_suffix(".sqlite3") if self.legacy_path else source
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        database = sqlite3.connect(self.path, timeout=5.0)
        database.row_factory = sqlite3.Row
        database.execute("PRAGMA busy_timeout=5000")
        return database

    def _initialize(self) -> None:
        with self._connect() as database:
            database.execute("PRAGMA journal_mode=WAL")
            database.executescript("""
                CREATE TABLE IF NOT EXISTS store_metadata (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_selections (
                    scope_key TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_selection_checkpoints (
                    tick_id TEXT PRIMARY KEY,
                    scope_key TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_transition_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    scope_key TEXT NOT NULL,
                    statework_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    expected_revision INTEGER NOT NULL,
                    before_revision INTEGER NOT NULL,
                    after_revision INTEGER,
                    outcome TEXT NOT NULL,
                    failure_class TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS workflow_transition_attempt_scope
                    ON workflow_transition_attempts(scope_key, started_at, attempt_id);
            """)
            database.execute("BEGIN IMMEDIATE")
            migrated = database.execute(
                "SELECT value FROM store_metadata WHERE key='legacy_json_import_v1'").fetchone()
            if migrated is None:
                try:
                    legacy = self._read_legacy()
                    for key, record in legacy["scopes"].items():
                        database.execute(
                            "INSERT OR IGNORE INTO workflow_selections "
                            "(scope_key, revision, record_json) VALUES (?, ?, ?)",
                            (key, int(record.get("revision", 0)),
                             json.dumps(record, sort_keys=True, separators=(",", ":"))))
                    database.execute(
                        "INSERT INTO store_metadata(key, value) VALUES (?, ?)",
                        ("legacy_json_import_v1", "complete"))
                except Exception:
                    database.rollback()
                    raise
            database.commit()
        os.chmod(self.path, 0o600)

    def begin_transition_attempt(self, scope: Mapping[str, Any], *,
                                 attempt_id: str, statework_id: str,
                                 step_id: str, expected_revision: int,
                                 before_revision: int) -> None:
        """Durably start an authority attempt before CSW evaluates a step."""
        key = self._scope_key(scope)
        if (not isinstance(attempt_id, str) or len(attempt_id) != 32
                or any(char not in "0123456789abcdef" for char in attempt_id)
                or not isinstance(statework_id, str) or not statework_id.strip()
                or len(statework_id) > 256
                or not isinstance(step_id, str) or not step_id.strip()
                or len(step_id) > 256
                or type(expected_revision) is not int or expected_revision < 0
                or type(before_revision) is not int or before_revision < 0):
            raise TransitionError("workflow transition attempt is malformed")
        started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        try:
            with self._connect() as database:
                database.execute(
                    "INSERT INTO workflow_transition_attempts "
                    "(attempt_id, scope_key, statework_id, step_id, expected_revision, "
                    "before_revision, after_revision, outcome, failure_class, started_at, "
                    "completed_at) VALUES (?, ?, ?, ?, ?, ?, NULL, 'pending', NULL, ?, NULL)",
                    (attempt_id, key, statework_id, step_id, expected_revision,
                     before_revision, started_at))
        except sqlite3.Error as exc:
            raise TransitionError("workflow transition attempt could not be recorded") from exc

    def finish_transition_attempt(self, attempt_id: str, *, outcome: str,
                                  after_revision: int | None,
                                  failure_class: str | None = None) -> None:
        """Close a started attempt with the authority's observed result."""
        if (not isinstance(attempt_id, str) or len(attempt_id) != 32
                or any(char not in "0123456789abcdef" for char in attempt_id)
                or outcome not in {"accepted", "rejected"}
                or (after_revision is not None
                    and (type(after_revision) is not int or after_revision < 0))
                or (failure_class is not None
                    and (not isinstance(failure_class, str)
                         or not failure_class.isidentifier()
                         or len(failure_class) > 96))):
            raise TransitionError("workflow transition result is malformed")
        completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._connect() as database:
            cursor = database.execute(
                "UPDATE workflow_transition_attempts SET after_revision=?, outcome=?, "
                "failure_class=?, completed_at=? WHERE attempt_id=? AND outcome='pending'",
                (after_revision, outcome, failure_class, completed_at, attempt_id))
            if cursor.rowcount != 1:
                raise TransitionError("workflow transition attempt is missing or already closed")

    def transition_attempt_summary(self, scope: Mapping[str, Any]) -> dict[str, Any]:
        """Return bounded, read-only transition evidence for one workflow scope."""
        key = self._scope_key(scope)
        with self._connect() as database:
            total = int(database.execute(
                "SELECT COUNT(*) FROM workflow_transition_attempts WHERE scope_key=?",
                (key,)).fetchone()[0])
            rows = database.execute(
                "SELECT attempt_id, statework_id, step_id, expected_revision, "
                "before_revision, after_revision, outcome, failure_class, started_at, "
                "completed_at FROM workflow_transition_attempts WHERE scope_key=? "
                "ORDER BY started_at, attempt_id LIMIT ?",
                (key, self.MAX_TRANSITION_AUDIT_ROWS)).fetchall()
        attempts = [{
            "attempt_id": str(row["attempt_id"]),
            "statework_id": str(row["statework_id"]),
            "step_id": str(row["step_id"]),
            "expected_revision": int(row["expected_revision"]),
            "before_revision": int(row["before_revision"]),
            "after_revision": (int(row["after_revision"])
                               if row["after_revision"] is not None else None),
            "outcome": str(row["outcome"]),
            "failure_class": row["failure_class"],
            "started_at": str(row["started_at"]),
            "completed_at": row["completed_at"],
        } for row in rows]
        counts = {outcome: sum(item["outcome"] == outcome for item in attempts)
                  for outcome in ("accepted", "rejected", "pending")}
        receipt_digest = hashlib.sha256(json.dumps(
            attempts, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False).encode("utf-8")).hexdigest()
        truncated = total > len(attempts)
        return {
            "schema_version": "csw-transition-attempts/v1",
            "status": "truncated" if truncated else "observed",
            "scope_sha256": hashlib.sha256(key.encode("utf-8")).hexdigest(),
            "attempt_count": total,
            "accepted_count": counts["accepted"],
            "rejected_count": counts["rejected"],
            "pending_count": counts["pending"],
            "truncated": truncated,
            "receipt_sha256": receipt_digest,
            "attempts": attempts,
        }

    def _read_legacy(self) -> dict[str, Any]:
        if self.legacy_path is None or not self.legacy_path.exists():
            return {"version": 2, "scopes": {}}
        try:
            value = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TransitionError("workflow selection store is unreadable") from exc
        if (not isinstance(value, dict) or value.get("version") not in {1, 2}
                or not isinstance(value.get("scopes"), dict)):
            raise TransitionError("workflow selection store has invalid structure")
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

    def create_checkpoint(self, scope: Mapping[str, Any], *, tick_id: str,
                          expected_revision: int) -> None:
        """Durably save the exact pre-tick selection before DP-owned writes."""
        if not isinstance(tick_id, str) or not tick_id or len(tick_id) > 256:
            raise TransitionError("workflow selection checkpoint tick ID is invalid")
        key = self._scope_key(scope)
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            row = database.execute(
                "SELECT record_json FROM workflow_selections WHERE scope_key=?", (key,)
            ).fetchone()
            record = (json.loads(row[0]) if row is not None else {
                "scope": {name: scope[name] for name in self.SCOPE_FIELDS},
                "revision": 0, "active_workflows": {},
            })
            if int(record["revision"]) != int(expected_revision):
                database.rollback()
                raise TransitionError(
                    "workflow selection changed before its reversible checkpoint")
            encoded = json.dumps(record, sort_keys=True, separators=(",", ":"))
            existing = database.execute(
                "SELECT scope_key, record_json FROM workflow_selection_checkpoints "
                "WHERE tick_id=?", (tick_id,)).fetchone()
            if existing is not None:
                if existing[0] != key or existing[1] != encoded:
                    database.rollback()
                    raise TransitionError("workflow checkpoint tick ID was reused")
            else:
                database.execute(
                    "INSERT INTO workflow_selection_checkpoints "
                    "(tick_id, scope_key, record_json) VALUES (?, ?, ?)",
                    (tick_id, key, encoded))
            database.commit()

    def restore_checkpoint(self, scope: Mapping[str, Any], *, tick_id: str,
                           expected_revision: int) -> dict[str, Any] | None:
        """CAS-restore exact ownership rows and consume the durable checkpoint."""
        key = self._scope_key(scope)
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            checkpoint = database.execute(
                "SELECT scope_key, record_json FROM workflow_selection_checkpoints "
                "WHERE tick_id=?", (tick_id,)).fetchone()
            if checkpoint is None:
                database.rollback()
                return None
            if checkpoint[0] != key:
                database.rollback()
                raise TransitionError("workflow checkpoint belongs to another scope")
            current = database.execute(
                "SELECT record_json FROM workflow_selections WHERE scope_key=?", (key,)
            ).fetchone()
            current_record = (json.loads(current[0]) if current is not None else {
                "scope": {name: scope[name] for name in self.SCOPE_FIELDS},
                "revision": 0, "active_workflows": {},
            })
            actual_revision = int(current_record["revision"])
            if actual_revision != int(expected_revision):
                database.rollback()
                raise TransitionError(
                    f"workflow selection restore conflict: expected {expected_revision}, "
                    f"found {actual_revision}; re-inspect required")
            restored = json.loads(checkpoint[1])
            restored["scope"] = {name: scope[name] for name in self.SCOPE_FIELDS}
            restored["revision"] = actual_revision + 1
            for row in restored["active_workflows"].values():
                self._validate_activation_row(row, max_revision=restored["revision"])
            database.execute(
                "INSERT INTO workflow_selections(scope_key, revision, record_json) "
                "VALUES (?, ?, ?) ON CONFLICT(scope_key) DO UPDATE SET "
                "revision=excluded.revision, record_json=excluded.record_json",
                (key, restored["revision"], json.dumps(
                    restored, sort_keys=True, separators=(",", ":"))))
            database.execute(
                "DELETE FROM workflow_selection_checkpoints WHERE tick_id=?", (tick_id,))
            database.commit()
        return copy.deepcopy(restored)

    def finalize_checkpoint(self, scope: Mapping[str, Any], *, tick_id: str) -> None:
        """Discard a checkpoint after DP has durably committed the tick."""
        key = self._scope_key(scope)
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            row = database.execute(
                "SELECT scope_key FROM workflow_selection_checkpoints WHERE tick_id=?",
                (tick_id,)).fetchone()
            if row is not None and row[0] != key:
                database.rollback()
                raise TransitionError("workflow checkpoint belongs to another scope")
            database.execute(
                "DELETE FROM workflow_selection_checkpoints WHERE tick_id=?", (tick_id,))
            database.commit()

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

    def get(self, scope: Mapping[str, Any]) -> dict[str, Any]:
        key = self._scope_key(scope)
        with self._connect() as database:
            row = database.execute(
                "SELECT record_json FROM workflow_selections WHERE scope_key=?", (key,)
            ).fetchone()
        record = (json.loads(row[0]) if row is not None else {
            "scope": {name: scope[name] for name in self.SCOPE_FIELDS},
            "revision": 0, "active_workflows": {},
        })
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
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            row = database.execute(
                "SELECT record_json FROM workflow_selections WHERE scope_key=?", (key,)
            ).fetchone()
            prior = json.loads(row[0]) if row is not None else {
                "scope": {name: scope[name] for name in self.SCOPE_FIELDS},
                "revision": 0, "active_workflows": {},
            }
            if int(prior.get("revision", 0)) != int(expected_revision):
                database.rollback()
                raise TransitionError(
                    f"workflow selection revision conflict: expected {expected_revision}, "
                    f"found {prior.get('revision', 0)}; re-inspect required")
            updated = {"scope": {name: scope[name] for name in self.SCOPE_FIELDS},
                       "revision": int(expected_revision) + 1,
                       "active_workflows": candidate}
            database.execute(
                "INSERT INTO workflow_selections(scope_key, revision, record_json) "
                "VALUES (?, ?, ?) ON CONFLICT(scope_key) DO UPDATE SET "
                "revision=excluded.revision, record_json=excluded.record_json",
                (key, updated["revision"],
                 json.dumps(updated, sort_keys=True, separators=(",", ":"))))
            database.commit()
        return copy.deepcopy(updated)

    @staticmethod
    def _validate_activation_row(row: Mapping[str, Any], *, max_revision: int) -> None:
        owner = row.get("activation_owner")
        if owner not in {"host", "digitalpsychology", "dependency"}:
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
        elif owner == "dependency":
            if (control_session_id is not None or intervention_id is not None
                    or expiry is not None):
                raise TransitionError(
                    "dependency-retained activation cannot carry an expired DP lease")
        elif (not isinstance(control_session_id, str) or not control_session_id
              or len(control_session_id) > 256
              or not isinstance(intervention_id, str) or not intervention_id
              or len(intervention_id) > 128
              or type(expiry) is not int or expiry < 0):
            raise TransitionError("DigitalPsychology workflow lease is malformed")
