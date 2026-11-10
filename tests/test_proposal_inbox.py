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


def test_idempotent_resubmit_returns_same_id(tmp_path):
    inbox = ProposalInbox(tmp_path / "inbox.json")
    payload = _proposal()
    first = inbox.submit(payload)
    second = inbox.submit(dict(payload))
    assert first == second
    assert inbox.open_count() == 1
    # Idempotent even after resolution: same id, no duplicate, no cap consumed.
    inbox.resolve(first, "accepted", host_note="done")
    assert inbox.submit(payload) == first
    assert inbox.open_count() == 0
    resolved = inbox.get(first)
    assert resolved["status"] == "resolved"
    assert resolved["resolution"]["outcome"] == "accepted"


def test_reopen_after_write_readable(tmp_path):
    inbox = ProposalInbox(tmp_path / "inbox.json")
    payloads = []
    for index in range(3):
        item = _proposal()
        item["body"] = {"n": index}
        payloads.append(item)
    ids = [inbox.submit(item) for item in payloads]
    inbox.resolve(ids[0], "rejected", host_note="dup")
    # Simulated crash: new handle on the same file with no explicit
    # checkpoint/close of the old handle must see all committed state.
    reopened = ProposalInbox(tmp_path / "inbox.json")
    assert reopened.open_count() == 2
    for pid in ids:
        assert reopened.get(pid)["proposal_id"] == pid
    assert reopened.get(ids[0])["status"] == "resolved"
    assert reopened.get(ids[0])["resolution"]["outcome"] == "rejected"


def test_torn_write_leaves_prior_state_readable(tmp_path):
    import sqlite3

    inbox = ProposalInbox(tmp_path / "inbox.json")
    committed = []
    for index in range(2):
        item = _proposal()
        item["body"] = {"committed": index}
        committed.append(inbox.submit(item))
    # Start an uncommitted write and abandon it (close without COMMIT),
    # simulating a crash mid-transaction. SQLite must roll it back.
    raw = sqlite3.connect(str(tmp_path / "inbox.json"), timeout=5.0,
                          isolation_level=None, check_same_thread=False)
    try:
        raw.execute("BEGIN IMMEDIATE;")
        raw.execute(
            "INSERT INTO proposals (proposal_id, kind, author_model,"
            " model_revision, subject_ref, body, submitted_at, status)"
            " VALUES ('prop-torn-write-probe', 'test_selection_draft',"
            " 'm', 'r', 's', '{\"x\":1}', 't', 'open')")
    finally:
        raw.close()  # no COMMIT: torn write is discarded
    reopened = ProposalInbox(tmp_path / "inbox.json")
    for pid in committed:
        assert reopened.get(pid)["proposal_id"] == pid
    with pytest.raises(TransitionError, match="unknown proposal"):
        reopened.get("prop-torn-write-probe")


def test_concurrent_submits_cap_holds(tmp_path, monkeypatch):
    import concurrent.futures
    import threading

    import proposal_inbox as pi

    monkeypatch.setattr(pi, "MAX_OPEN_PROPOSALS", 10)
    inbox = ProposalInbox(tmp_path / "inbox.json")
    errors: list = []
    won: list = []
    lock = threading.Lock()

    def _submit(index: int):
        item = _proposal()
        item["body"] = {"race": index}
        try:
            pid = inbox.submit(item)
            with lock:
                won.append(pid)
            return ("ok", pid)
        except TransitionError as exc:
            with lock:
                errors.append(str(exc))
            return ("full", None)

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(_submit, range(30)))
    assert inbox.open_count() == 10
    assert len({pid for status, pid in results if status == "ok"}) == 10
    assert errors, "expected some submitters to fail closed once full"
    assert all("inbox is full" in message for message in errors)
    # Cap also holds through a second inbox handle on the same file.
    assert ProposalInbox(tmp_path / "inbox.json").open_count() == 10


def test_concurrent_submit_and_resolve_no_lost_updates(tmp_path):
    import concurrent.futures

    inbox = ProposalInbox(tmp_path / "inbox.json")
    count = 20
    payloads = []
    for index in range(count):
        item = _proposal()
        item["body"] = {"job": index}
        payloads.append(item)

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        submitted = list(pool.map(inbox.submit, payloads))
    assert len(set(submitted)) == count
    assert inbox.open_count() == count

    def _resolve(pid: str):
        return inbox.resolve(pid, "accepted", host_note=f"ok {pid}")["proposal_id"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        resolved = list(pool.map(_resolve, submitted))
    assert sorted(resolved) == sorted(submitted)
    assert inbox.open_count() == 0
    for pid in submitted:
        record = inbox.get(pid)
        assert record["status"] == "resolved"
        assert record["resolution"]["outcome"] == "accepted"

    # Resolve race on one proposal: exactly one CAS wins (CAS = single row).
    inbox2 = ProposalInbox(tmp_path / "race.sqlite")
    pid = inbox2.submit(_proposal())
    outcomes: list = []
    failures: list = []

    def _race(outcome: str):
        try:
            inbox2.resolve(pid, outcome, host_note=outcome)
            outcomes.append(outcome)
        except TransitionError as exc:
            failures.append(str(exc))

    import threading

    threads = [threading.Thread(target=_race, args=(outcome,))
               for outcome in ("accepted", "rejected", "expired")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(outcomes) == 1
    assert len(failures) == 2
    assert all("already resolved" in message for message in failures)
    final = inbox2.get(pid)
    assert final["status"] == "resolved"
    assert final["resolution"]["outcome"] == outcomes[0]
