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
"""

from __future__ import annotations

import hashlib
import json
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


class ProposalInbox:
    """Bounded file-backed store for model proposals. Host bookkeeping only."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._records: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise TransitionError("proposal inbox is unreadable") from exc
            if not isinstance(raw, Mapping):
                raise TransitionError("proposal inbox is malformed")
            for key, value in dict(raw).items():
                if isinstance(value, Mapping):
                    self._records[str(key)] = dict(value)

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._records, indent=2, sort_keys=True),
                             encoding="utf-8")

    def open_count(self) -> int:
        return sum(1 for item in self._records.values() if item.get("status") == "open")

    def submit(self, payload: Mapping[str, Any]) -> str:
        """Accept one proposal. Idempotent on identical content. Fail closed when full."""
        record = validate_proposal(payload)
        pid = proposal_id(record)
        if pid in self._records:
            return pid
        if self.open_count() >= MAX_OPEN_PROPOSALS:
            raise TransitionError("proposal inbox is full; resolve open proposals first")
        record["proposal_id"] = pid
        self._records[pid] = record
        self._persist()
        return pid

    def get(self, pid: str) -> dict[str, Any]:
        record = self._records.get(str(pid))
        if record is None:
            raise TransitionError(f"unknown proposal {pid!r}")
        return dict(record)

    def list_open(self, statework_id: str | None = None) -> list[dict[str, Any]]:
        out = [dict(item) for item in self._records.values()
               if item.get("status") == "open"
               and (statework_id is None or item.get("statework_id") == statework_id)]
        return sorted(out, key=lambda item: item["submitted_at"])

    def resolve(self, pid: str, outcome: str, host_note: str = "") -> dict[str, Any]:
        """Record the host's decision on a proposal. Bookkeeping only."""
        if outcome not in RESOLUTIONS:
            raise TransitionError(f"proposal resolution must be one of {sorted(RESOLUTIONS)}")
        if host_note and len(host_note) > MAX_NOTE_BYTES:
            raise TransitionError("proposal host note exceeds size bound")
        record = self._records.get(str(pid))
        if record is None:
            raise TransitionError(f"unknown proposal {pid!r}")
        if record.get("status") != "open":
            raise TransitionError(f"proposal {pid!r} is already resolved")
        record["status"] = "resolved"
        record["resolution"] = {
            "outcome": outcome,
            "host_note": host_note,
            "resolved_at": _utcnow(),
        }
        self._persist()
        return dict(record)


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
