"""Host-side model proposal inbox.

A semantic provider (JEV, Laya, or any future model) submits proposal
artifacts here: partition drafts, integration plan drafts, test selection
drafts, staleness flags. The host (or operator) reviews each proposal,
performs its OWN independent observation, and attests its OWN evidence
that references the proposal id as input.

This module is deliberately NOT workflow state and NOT evidence:

- Proposal ids are not evidence refs. The EvidenceStore never sees them.
  Passing a proposal id to WorkflowAuthority.apply_step fails closed
  (unknown evidence reference) with no state advance.
- Only EvidenceStore.create mints digests, and build_host_attestation
  refuses any non-host issuer. A model cannot attest.
- Resolving a proposal (accepted / rejected / expired) is host
  bookkeeping. It never transitions workflow state.

Separation: CSW core stays model-free. All model influence enters
through host attestation, exactly like any other untrusted input.

Persistence: SQLite in WAL mode. Each mutation runs in a single-writer
transaction (BEGIN IMMEDIATE) on its own connection with a busy timeout,
so concurrent threads/processes serialize instead of losing updates.
Payload columns are write-once (INSERT only); only status/outcome/
host_note/resolved_at are ever UPDATEd, and resolution is a
compare-and-swap (UPDATE ... WHERE status='open').
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from errors import TransitionError

PROPOSAL_KINDS = frozenset({
    "partition_draft",
    "integration_plan_draft",
    "test_selection_draft",
    "staleness_flag",
})

# Suggested owner per kind. Advisory only; the host decides routing.
PROPOSAL_OWNERS = {
    "partition_draft": "godkiller",
    "integration_plan_draft": "terraformer",
    "test_selection_draft": "testworks",
    "staleness_flag": None,
}

RESOLUTIONS = frozenset({"accepted", "rejected", "expired"})

MAX_OPEN_PROPOSALS = 128
MAX_TEXT_FIELD = 512
MAX_PAYLOAD_BYTES = 8192
MAX_NOTE_BYTES = 1024

_SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
  proposal_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  author_model TEXT NOT NULL,
  model_revision TEXT NOT NULL,
  subject_ref TEXT NOT NULL,
  statework_id TEXT,
  suggested_owner TEXT,
  body TEXT NOT NULL,
  basis_revision INTEGER,
  submitted_at TEXT NOT NULL,
  status TEXT NOT NULL,
  outcome TEXT,
  host_note TEXT NOT NULL DEFAULT '',
  resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str).encode("utf-8")


def _bounded_text(name: str, value: Any, limit: int = MAX_TEXT_FIELD) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise TransitionError(f"proposal field {name!r} must be bounded non-empty text")
    return value


def validate_proposal(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a model proposal; return the normalized record (no id yet)."""
    if not isinstance(payload, Mapping):
        raise TransitionError("proposal must be a mapping")
    kind = payload.get("kind")
    if kind not in PROPOSAL_KINDS:
        raise TransitionError(f"proposal kind must be one of {sorted(PROPOSAL_KINDS)}")
    author_model = _bounded_text("author_model", payload.get("author_model"))
    model_revision = _bounded_text("model_revision", payload.get("model_revision"), 128)
    subject_ref = _bounded_text("subject_ref", payload.get("subject_ref"))
    statework_id = payload.get("statework_id")
    if statework_id is not None:
        statework_id = _bounded_text("statework_id", statework_id, 64)
    body = payload.get("body")
    if not isinstance(body, Mapping) or not body:
        raise TransitionError("proposal body must be a non-empty mapping")
    if len(_canonical(body)) > MAX_PAYLOAD_BYTES:
        raise TransitionError("proposal body exceeds size bound")
    basis_revision = payload.get("basis_revision")
    if basis_revision is not None and (
            not isinstance(basis_revision, int) or basis_revision < 0):
        raise TransitionError("proposal basis_revision must be a non-negative int or absent")
    return {
        "kind": kind,
        "author_model": author_model,
        "model_revision": model_revision,
        "subject_ref": subject_ref,
        "statework_id": statework_id,
        "suggested_owner": PROPOSAL_OWNERS[kind],
        "body": json.loads(_canonical(body)),
        "basis_revision": basis_revision,
        "submitted_at": _utcnow(),
        "status": "open",
        "resolution": None,
    }


def proposal_id(record: Mapping[str, Any]) -> str:
    """Stable id over the proposal content (excludes status/resolution)."""
    basis = {key: record[key] for key in (
        "kind", "author_model", "model_revision", "subject_ref",
        "statework_id", "body", "basis_revision")}
    return "prop-" + hashlib.sha256(_canonical(basis)).hexdigest()[:24]


def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    resolution = None
    if row["status"] != "open":
        resolution = {
            "outcome": row["outcome"],
            "host_note": row["host_note"] or "",
            "resolved_at": row["resolved_at"],
        }
    return {
        "kind": row["kind"],
        "author_model": row["author_model"],
        "model_revision": row["model_revision"],
        "subject_ref": row["subject_ref"],
        "statework_id": row["statework_id"],
        "suggested_owner": row["suggested_owner"],
        "body": json.loads(row["body"]),
        "basis_revision": row["basis_revision"],
        "submitted_at": row["submitted_at"],
        "status": row["status"],
        "resolution": resolution,
        "proposal_id": row["proposal_id"],
    }


class ProposalInbox:
    """SQLite-WAL-backed store for model proposals. Host bookkeeping only."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._init_db()

    # -- internals -----------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(self.path), timeout=30.0,
                              isolation_level=None, check_same_thread=False)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute("PRAGMA synchronous=NORMAL;")
            con.execute("PRAGMA busy_timeout=30000;")
        except sqlite3.DatabaseError as exc:
            con.close()
            raise TransitionError("proposal inbox is unreadable") from exc
        return con

    def _init_db(self) -> None:
        try:
            con = self._connect()
        except TransitionError:
            raise
        try:
            try:
                con.executescript(_SCHEMA)
            except sqlite3.DatabaseError:
                # Existing file is not a SQLite db. If it is a legacy JSON
                # inbox, migrate its records; otherwise fail closed.
                con.close()
                self._migrate_legacy_json_or_raise()
                con = self._connect()
                con.executescript(_SCHEMA)
                con.close()
                return
            con.close()
        except sqlite3.DatabaseError as exc:
            try:
                con.close()
            except Exception:
                pass
            raise TransitionError("proposal inbox is unreadable") from exc

    def _migrate_legacy_json_or_raise(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TransitionError("proposal inbox is unreadable") from exc
        if not isinstance(raw, Mapping):
            raise TransitionError("proposal inbox is malformed")
        # Move the legacy file aside so the path names a SQLite file.
        backup = self.path.with_suffix(self.path.suffix + ".legacy-json-bak")
        try:
            self.path.rename(backup)
        except OSError as exc:
            raise TransitionError("proposal inbox is unreadable") from exc
        con = self._connect()
        try:
            con.executescript(_SCHEMA)
            for key, value in dict(raw).items():
                if not isinstance(value, Mapping):
                    continue
                try:
                    rec = dict(value)
                    pid = str(key)
                    body = rec.get("body", {})
                    resolution = rec.get("resolution") or {}
                    con.execute(
                        "INSERT OR IGNORE INTO proposals"
                        " (proposal_id, kind, author_model, model_revision,"
                        " subject_ref, statework_id, suggested_owner, body,"
                        " basis_revision, submitted_at, status, outcome,"
                        " host_note, resolved_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (pid, rec.get("kind"), rec.get("author_model"),
                         rec.get("model_revision"), rec.get("subject_ref"),
                         rec.get("statework_id"), rec.get("suggested_owner"),
                         _canonical(body).decode("utf-8"),
                         rec.get("basis_revision"), rec.get("submitted_at", _utcnow()),
                         rec.get("status", "open"), resolution.get("outcome"),
                         resolution.get("host_note", ""), resolution.get("resolved_at")),
                    )
                except sqlite3.DatabaseError:
                    continue
            con.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        finally:
            con.close()

    # -- reads ---------------------------------------------------------
    def open_count(self) -> int:
        con = self._connect()
        try:
            try:
                cur = con.execute("SELECT COUNT(*) FROM proposals WHERE status='open'")
            except sqlite3.DatabaseError as exc:
                raise TransitionError("proposal inbox is unreadable") from exc
            return int(cur.fetchone()[0])
        finally:
            con.close()

    def get(self, pid: str) -> dict[str, Any]:
        con = self._connect()
        try:
            try:
                cur = con.execute("SELECT * FROM proposals WHERE proposal_id=?", (str(pid),))
            except sqlite3.DatabaseError as exc:
                raise TransitionError("proposal inbox is unreadable") from exc
            row = cur.fetchone()
            if row is None:
                raise TransitionError(f"unknown proposal {pid!r}")
            return _row_to_record(row)
        finally:
            con.close()

    def list_open(self, statework_id: str | None = None) -> list[dict[str, Any]]:
        con = self._connect()
        try:
            try:
                if statework_id is None:
                    cur = con.execute(
                        "SELECT * FROM proposals WHERE status='open' ORDER BY submitted_at")
                else:
                    cur = con.execute(
                        "SELECT * FROM proposals WHERE status='open'"
                        " AND statework_id=? ORDER BY submitted_at", (statework_id,))
            except sqlite3.DatabaseError as exc:
                raise TransitionError("proposal inbox is unreadable") from exc
            return [_row_to_record(row) for row in cur.fetchall()]
        finally:
            con.close()

    # -- writes (single-writer transactions) ---------------------------
    def submit(self, payload: Mapping[str, Any]) -> str:
        """Accept one proposal. Idempotent on identical content. Fail closed when full."""
        record = validate_proposal(payload)
        pid = proposal_id(record)
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE;")
            try:
                cur = con.execute("SELECT status FROM proposals WHERE proposal_id=?", (pid,))
                if cur.fetchone() is not None:
                    # Idempotent resubmit: payload columns are immutable, so a
                    # matching id means identical content; return it unchanged.
                    con.execute("COMMIT;")
                    return pid
                cur = con.execute("SELECT COUNT(*) FROM proposals WHERE status='open'")
                if int(cur.fetchone()[0]) >= MAX_OPEN_PROPOSALS:
                    con.execute("ROLLBACK;")
                    raise TransitionError("proposal inbox is full; resolve open proposals first")
                con.execute(
                    "INSERT OR IGNORE INTO proposals"
                    " (proposal_id, kind, author_model, model_revision,"
                    " subject_ref, statework_id, suggested_owner, body,"
                    " basis_revision, submitted_at, status, outcome,"
                    " host_note, resolved_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', NULL, '', NULL)",
                    (pid, record["kind"], record["author_model"],
                     record["model_revision"], record["subject_ref"],
                     record["statework_id"], record["suggested_owner"],
                     _canonical(record["body"]).decode("utf-8"),
                     record["basis_revision"], record["submitted_at"]),
                )
                con.execute("COMMIT;")
                return pid
            except TransitionError:
                raise
            except sqlite3.DatabaseError as exc:
                try:
                    con.execute("ROLLBACK;")
                except Exception:
                    pass
                raise TransitionError("proposal inbox write failed") from exc
        finally:
            con.close()

    def resolve(self, pid: str, outcome: str, host_note: str = "") -> dict[str, Any]:
        """Record the host's decision on a proposal. Bookkeeping only."""
        if outcome not in RESOLUTIONS:
            raise TransitionError(f"proposal resolution must be one of {sorted(RESOLUTIONS)}")
        if host_note and len(host_note) > MAX_NOTE_BYTES:
            raise TransitionError("proposal host note exceeds size bound")
        pid = str(pid)
        resolved_at = _utcnow()
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE;")
            try:
                # CAS: only an open row may transition; rowcount 0 means
                # unknown or already resolved.
                cur = con.execute(
                    "UPDATE proposals SET status='resolved', outcome=?,"
                    " host_note=?, resolved_at=? WHERE proposal_id=? AND status='open'",
                    (outcome, host_note, resolved_at, pid),
                )
                if cur.rowcount == 0:
                    probe = con.execute(
                        "SELECT status FROM proposals WHERE proposal_id=?", (pid,)).fetchone()
                    con.execute("ROLLBACK;")
                    if probe is None:
                        raise TransitionError(f"unknown proposal {pid!r}")
                    raise TransitionError(f"proposal {pid!r} is already resolved")
                con.execute("COMMIT;")
            except TransitionError:
                raise
            except sqlite3.DatabaseError as exc:
                try:
                    con.execute("ROLLBACK;")
                except Exception:
                    pass
                raise TransitionError("proposal inbox write failed") from exc
            return self.get(pid)
        finally:
            con.close()


def build_host_attestation(proposal: Mapping[str, Any], *, ref: str, kind: str,
                           subject_ref: str, observed_at: str, issuer: str,
                           validator: str, schema: str,
                           host_observation: Mapping[str, Any]) -> dict[str, Any]:
    """Build a host evidence record that cites a proposal as INPUT.

    The issuer must be a host issuer (host:...). A model issuer is
    rejected: models propose, only hosts attest. The proposal content is
    folded into content_digest so the attestation is bound to the exact
    proposal reviewed, but the evidence stands on the host's own
    observation, which the caller supplies and is responsible for.
    """
    if not isinstance(issuer, str) or not issuer.startswith("host:"):
        raise TransitionError("proposal-linked evidence must carry a host issuer")
    if not isinstance(host_observation, Mapping) or not host_observation:
        raise TransitionError("host observation must be a non-empty mapping")
    pid = proposal.get("proposal_id") or proposal_id(validate_proposal(proposal))
    content_digest = hashlib.sha256(
        _canonical({"ref": ref, "proposal_id": pid, "observation": host_observation})
    ).hexdigest()
    return {
        "ref": _bounded_text("ref", ref, 256),
        "kind": _bounded_text("kind", kind, 128),
        "subject_ref": _bounded_text("subject_ref", subject_ref),
        "observed_at": _bounded_text("observed_at", observed_at, 64),
        "issuer": issuer,
        "validator": validator,
        "schema": schema,
        "content_digest": content_digest,
        "proposal_id": pid,
        "proposal_author": f"{proposal.get('author_model')}:{proposal.get('model_revision')}",
    }


__all__ = [
    "PROPOSAL_KINDS",
    "PROPOSAL_OWNERS",
    "RESOLUTIONS",
    "MAX_OPEN_PROPOSALS",
    "ProposalInbox",
    "build_host_attestation",
    "proposal_id",
    "validate_proposal",
]
