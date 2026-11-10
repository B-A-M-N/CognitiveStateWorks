"""Proposal inbox: a model proposal alone must never advance workflow state.

Only host attestation that cites a proposal as input can satisfy a
transition guard. The host remains the decider.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from errors import TransitionError
from evidence import EvidenceStore
from proposal_inbox import (
    ProposalInbox,
    build_host_attestation,
    validate_proposal,
)
from selection_store import WorkflowSelectionStore
from state_store import SubjectStateStore
from workflow_authority import WorkflowAuthority
from workflow_engines import WorkflowIdentity


def _host(tmp_path: Path):
    evidence = EvidenceStore()
    authority = WorkflowAuthority(
        root=ROOT,
        state_store=SubjectStateStore(tmp_path / "subjects.json"),
        evidence_store=evidence,
        selection_store=WorkflowSelectionStore(tmp_path / "selections.json"),
    )
    contract = authority.workflow_contract_identity("testworks")
    identity = WorkflowIdentity(
        namespace_id="qualification-tenant",
        application_id="csw-qualification",
        application_instance_id="csw-qualification-v1",
        workflow_id="testworks-proposal-qualification",
        subject_ref="proposal:testworks:subject",
        statework_id="testworks",
        contract_version=contract["contract_version"],
    )
    return authority, evidence, identity, contract


def _proposal(subject_ref: str = "proposal:testworks:subject") -> dict:
    return {
        "kind": "test_selection_draft",
        "author_model": "typesafe/jev-1.14",
        "model_revision": "jev-1.14",
        "subject_ref": subject_ref,
        "statework_id": "testworks",
        "body": {"recommended": ["smoke", "contract"], "omitted": ["full-suite"]},
        "basis_revision": 3,
    }


def _host_record(authority, identity, proposal, kind="testworks.inventory") -> dict:
    spec = authority._compiled_registry["evidence_registry"]["kinds"][kind]
    return build_host_attestation(
        proposal,
        ref=f"proposal-link:{kind}:{hashlib.sha256(kind.encode()).hexdigest()[:8]}",
        kind=kind,
        subject_ref=identity.subject_ref,
        observed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        issuer=spec["allowed_issuers"][0],
        validator=spec["validator"],
        schema=spec["schema"],
        host_observation={"checked": "ran smoke + contract on current revision"},
    )


def test_proposal_alone_advances_nothing(tmp_path):
    authority, _evidence, identity, contract = _host(tmp_path)
    inbox = ProposalInbox(tmp_path / "inbox.json")
    pid = inbox.submit(_proposal())
    snapshot = authority.inspect_workflow(identity, contract_hash=contract["contract_hash"])
    with pytest.raises(TransitionError, match="not present in the trusted store"):
        authority.apply_step(
            identity, contract_hash=contract["contract_hash"],
            step_id="testworks.unassessed.inventory.inventoried",
            evidence_refs=[pid], expected_revision=snapshot.revision)
    assert authority.inspect_workflow(
        identity, contract_hash=contract["contract_hash"]).revision == snapshot.revision


def test_host_attestation_citing_proposal_advances(tmp_path):
    authority, evidence, identity, contract = _host(tmp_path)
    inbox = ProposalInbox(tmp_path / "inbox.json")
    pid = inbox.submit(_proposal())
    proposal = inbox.get(pid)
    record = _host_record(authority, identity, proposal)
    assert record["proposal_id"] == pid
    assert record["issuer"].startswith("host:")
    ref = evidence.create(record)
    snapshot = authority.inspect_workflow(identity, contract_hash=contract["contract_hash"])
    decision = authority.apply_step(
        identity, contract_hash=contract["contract_hash"],
        step_id="testworks.unassessed.inventory.inventoried",
        evidence_refs=[ref], expected_revision=snapshot.revision)
    assert decision.allowed is True
    resolved = inbox.resolve(pid, "accepted", host_note="verified smoke + contract receipts")
    assert resolved["status"] == "resolved"
    assert resolved["resolution"]["outcome"] == "accepted"


def test_model_issuer_is_rejected(tmp_path):
    inbox = ProposalInbox(tmp_path / "inbox.json")
    pid = inbox.submit(_proposal())
    with pytest.raises(TransitionError, match="must carry a host issuer"):
        build_host_attestation(
            inbox.get(pid), ref="x", kind="testworks.inventory",
            subject_ref="s", observed_at="t", issuer="model:jev-1.14",
            validator="v", schema="s", host_observation={"a": "b"})


def test_malformed_proposals_rejected(tmp_path):
    inbox = ProposalInbox(tmp_path / "inbox.json")
    base = _proposal()
    bad_kind = dict(base, kind="mind_control")
    with pytest.raises(TransitionError):
        inbox.submit(bad_kind)
    no_author = dict(base)
    del no_author["author_model"]
    with pytest.raises(TransitionError):
        inbox.submit(no_author)
    huge = dict(base, body={"blob": "x" * 9000})
    with pytest.raises(TransitionError):
        inbox.submit(huge)
    bad_basis = dict(base, basis_revision=-1)
    with pytest.raises(TransitionError):
        inbox.submit(bad_basis)
    with pytest.raises(TransitionError):
        validate_proposal("not-a-mapping")


def test_inbox_is_bounded_and_resolving_frees_capacity(tmp_path, monkeypatch):
    import proposal_inbox as pi
    monkeypatch.setattr(pi, "MAX_OPEN_PROPOSALS", 3)
    inbox = ProposalInbox(tmp_path / "inbox.json")
    ids = []
    for index in range(3):
        item = _proposal()
        item["body"] = {"n": index}
        ids.append(inbox.submit(item))
    with pytest.raises(TransitionError, match="inbox is full"):
        inbox.submit({**_proposal(), "body": {"n": "overflow"}})
    inbox.resolve(ids[0], "rejected", host_note="duplicate")
    item = _proposal()
    item["body"] = {"n": "after-resolve"}
    assert inbox.submit(item)
    assert inbox.open_count() == 3


def test_staleness_flag_never_transitions(tmp_path):
    authority, _evidence, identity, contract = _host(tmp_path)
    inbox = ProposalInbox(tmp_path / "inbox.json")
    pid = inbox.submit({**_proposal(), "kind": "staleness_flag", "statework_id": None})
    assert inbox.get(pid)["suggested_owner"] is None
    snapshot = authority.inspect_workflow(identity, contract_hash=contract["contract_hash"])
    decision = authority.apply_step(
        identity, contract_hash=contract["contract_hash"],
        step_id="testworks.unassessed.inventory.inventoried",
        evidence_refs=[], expected_revision=snapshot.revision)
    assert decision.allowed is False
    assert authority.inspect_workflow(
        identity, contract_hash=contract["contract_hash"]).revision == snapshot.revision
