from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from errors import TransitionError
from evidence import EvidenceStore
from selection_store import WorkflowSelectionStore
from state_store import SubjectStateStore
from workflow_authority import WorkflowAuthority
from workflow_engines import WorkflowIdentity


SCENARIOS = {
    "godkiller": {
        "positive": {
            "legitimate-central-authority",
            "shared-state-invariant",
        },
        "negative": {"cosmetic-split", "stale-revision"},
    },
    "terraformer": {
        "positive": {"already-coherent", "partial-lifecycle"},
        "negative": {"unnecessary-adapter", "conflicting-ownership"},
    },
    "testworks": {
        "positive": {"sufficient-evidence", "stale-receipts-run-selected"},
        "negative": {"green-from-another-subject", "critical-gate-omitted"},
    },
}


def _host(tmp_path: Path, statework_id: str):
    evidence = EvidenceStore()
    state_path = tmp_path / f"{statework_id}-subjects.json"
    selection_path = tmp_path / f"{statework_id}-selections.json"
    authority = WorkflowAuthority(
        root=ROOT,
        state_store=SubjectStateStore(state_path),
        evidence_store=evidence,
        selection_store=WorkflowSelectionStore(selection_path),
    )
    contract_identity = authority.workflow_contract_identity(statework_id)
    identity = WorkflowIdentity(
        namespace_id="qualification-tenant",
        application_id="csw-qualification",
        application_instance_id="csw-qualification-v1",
        workflow_id=f"{statework_id}-host-qualification",
        subject_ref=f"architecture:{statework_id}:qualification-subject",
        statework_id=statework_id,
        contract_version=contract_identity["contract_version"],
    )
    return authority, evidence, identity, contract_identity


def _attest(authority: WorkflowAuthority, identity: WorkflowIdentity,
            statework_id: str, kind: str, *, issuer: str | None = None) -> str:
    registry = authority._compiled_registry["evidence_registry"]["kinds"]
    spec = registry[kind]
    ref = f"qualification:{statework_id}:{kind}:{hashlib.sha256(kind.encode()).hexdigest()[:10]}:{datetime.now(timezone.utc).timestamp()}"
    record = {
        "ref": ref,
        "kind": kind,
        "subject_ref": identity.subject_ref,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "issuer": issuer or spec["allowed_issuers"][0],
        "validator": spec["validator"],
        "schema": spec["schema"],
        "content_digest": hashlib.sha256(ref.encode()).hexdigest(),
    }
    return authority.evidence_store.create(record)


def _apply(authority: WorkflowAuthority, identity: WorkflowIdentity,
           contract_hash: str, snapshot, step_id: str,
           evidence_kinds: tuple[str, ...]):
    refs = [_attest(authority, identity, identity.statework_id, kind)
            for kind in evidence_kinds]
    decision = authority.apply_step(
        identity, contract_hash=contract_hash, step_id=step_id,
        evidence_refs=refs, expected_revision=snapshot.revision)
    return decision, refs, authority.inspect_workflow(
        identity, contract_hash=contract_hash)


@pytest.mark.parametrize("statework_id", ["godkiller", "terraformer", "testworks"])
def test_host_requires_registered_attested_evidence_and_current_revision(
        tmp_path, statework_id):
    authority, _evidence, identity, contract = _host(tmp_path, statework_id)
    contract_hash = contract["contract_hash"]
    snapshot = authority.inspect_workflow(identity, contract_hash=contract_hash)
    assert snapshot.revision > 0

    initial_step = {
        "godkiller": "godkiller.unassessed.observe.mapped",
        "terraformer": "terraformer.unassessed.validate_contracts.contracts_validated",
        "testworks": "testworks.unassessed.inventory.inventoried",
    }[statework_id]
    initial_evidence = {
        "godkiller": ("godkiller.inventory",),
        "terraformer": ("terraformer.inventory", "terraformer.contract_validation"),
        "testworks": ("testworks.inventory",),
    }[statework_id]

    missing = authority.apply_step(
        identity, contract_hash=contract_hash, step_id=initial_step,
        evidence_refs=[], expected_revision=snapshot.revision)
    assert missing.allowed is False
    assert authority.inspect_workflow(identity, contract_hash=contract_hash).revision == snapshot.revision

    foreign_ref = _attest(
        authority, identity, statework_id, initial_evidence[0], issuer="model:assertion")
    foreign = authority.apply_step(
        identity, contract_hash=contract_hash, step_id=initial_step,
        evidence_refs=[foreign_ref], expected_revision=snapshot.revision)
    assert foreign.allowed is False
    assert "missing evidence kinds" in foreign.reason

    decision, _refs, advanced = _apply(
        authority, identity, contract_hash, snapshot, initial_step, initial_evidence)
    assert decision.allowed is True
    assert advanced.revision == snapshot.revision + 1
    assert advanced.current_state == {
        "godkiller": "MAPPED",
        "terraformer": "CONTRACTS_VALIDATED",
        "testworks": "INVENTORIED",
    }[statework_id]

    with pytest.raises(TransitionError, match="revision conflict"):
        authority.apply_step(
            identity, contract_hash=contract_hash, step_id=initial_step,
            evidence_refs=[], expected_revision=snapshot.revision)
    assert authority.inspect_workflow(identity, contract_hash=contract_hash).revision == advanced.revision


@pytest.mark.parametrize("statework_id", ["godkiller", "terraformer", "testworks"])
def test_host_accepts_evidence_backed_negative_decision_then_reopens_and_recovers(
        tmp_path, statework_id):
    authority, evidence, identity, contract = _host(tmp_path, statework_id)
    contract_hash = contract["contract_hash"]
    snapshot = authority.inspect_workflow(identity, contract_hash=contract_hash)

    first_step = {
        "godkiller": "godkiller.unassessed.observe.mapped",
        "terraformer": "terraformer.unassessed.validate_contracts.contracts_validated",
        "testworks": "testworks.unassessed.inventory.inventoried",
    }[statework_id]
    first_kinds = {
        "godkiller": ("godkiller.inventory",),
        "terraformer": ("terraformer.inventory", "terraformer.contract_validation"),
        "testworks": ("testworks.inventory",),
    }[statework_id]
    decision, _refs, snapshot = _apply(
        authority, identity, contract_hash, snapshot, first_step, first_kinds)
    assert decision.allowed and not snapshot.completed

    if statework_id == "testworks":
        decision, _refs, snapshot = _apply(
            authority, identity, contract_hash, snapshot,
            "testworks.inventoried.strategize.strategized",
            ("testworks.strategy", "testworks.risk_assessment"))
        assert decision.allowed and not snapshot.completed

    terminal_step = {
        "godkiller": "godkiller.mapped.no_action.no_decomposition_needed",
        "terraformer": "terraformer.contracts_validated.no_action.no_composition_needed",
        "testworks": "testworks.strategized.decline.no_additional_testing_needed",
    }[statework_id]
    terminal_kinds = {
        "godkiller": ("godkiller.no_action", "godkiller.baseline"),
        "terraformer": ("terraformer.no_action", "terraformer.contract_validation"),
        "testworks": ("testworks.sufficiency", "testworks.subject_identity"),
    }[statework_id]
    decision, terminal_refs, completed = _apply(
        authority, identity, contract_hash, snapshot, terminal_step, terminal_kinds)
    assert decision.allowed and completed.completed

    evidence.invalidate(terminal_refs[0])
    reopened = authority.inspect_workflow(identity, contract_hash=contract_hash)
    assert reopened.completed is False
    assert reopened.current_state == {
        "godkiller": "MAPPED",
        "terraformer": "CONTRACTS_VALIDATED",
        "testworks": "STRATEGIZED",
    }[statework_id]
    assert reopened.revision > completed.revision

    invalidation_kind = f"{statework_id}.invalidation"
    invalidation_ref = _attest(authority, identity, statework_id, invalidation_kind)
    invalidation_step = {
        "godkiller": "godkiller.any.invalidate.invalidated",
        "terraformer": "terraformer.any.invalidate.invalidated",
        "testworks": "testworks.strategized.invalidate.invalidated",
    }[statework_id]
    invalidated = authority.apply_step(
        identity, contract_hash=contract_hash, step_id=invalidation_step,
        evidence_refs=[invalidation_ref], expected_revision=reopened.revision)
    assert invalidated.allowed
    assert invalidated.current_state == "INVALIDATED"

    recovery_step = {
        "godkiller": "godkiller.invalidated.reobserve.mapped",
        "terraformer": "terraformer.invalidated.reobserve.unassessed",
        "testworks": "testworks.invalidated.reassess.unassessed",
    }[statework_id]
    recovery_kinds = {
        "godkiller": ("godkiller.invalidation", "godkiller.inventory"),
        "terraformer": ("terraformer.invalidation", "terraformer.inventory"),
        "testworks": ("testworks.reassessment",),
    }[statework_id]
    recovered_snapshot = authority.inspect_workflow(identity, contract_hash=contract_hash)
    recovery_refs = [invalidation_ref] + [
        _attest(authority, identity, statework_id, kind)
        for kind in recovery_kinds if kind != invalidation_kind]
    recovered = authority.apply_step(
        identity, contract_hash=contract_hash, step_id=recovery_step,
        evidence_refs=recovery_refs, expected_revision=recovered_snapshot.revision)
    assert recovered.allowed
    assert recovered.current_state == {
        "godkiller": "MAPPED",
        "terraformer": "UNASSESSED",
        "testworks": "UNASSESSED",
    }[statework_id]


@pytest.mark.parametrize("statework_id", ["godkiller", "terraformer", "testworks"])
def test_consequential_step_rejects_evidence_from_before_state_entry(
        tmp_path, statework_id):
    authority, _evidence, identity, contract = _host(tmp_path, statework_id)
    contract_hash = contract["contract_hash"]
    snapshot = authority.inspect_workflow(identity, contract_hash=contract_hash)

    def advance(step_id, kinds):
        nonlocal snapshot
        decision, _refs, snapshot = _apply(
            authority, identity, contract_hash, snapshot, step_id, kinds)
        assert decision.allowed

    if statework_id == "godkiller":
        advance("godkiller.unassessed.observe.mapped", ("godkiller.inventory",))
        advance("godkiller.mapped.diagnose.diagnosed", ("godkiller.diagnosis",))
        stale_authority = _attest(authority, identity, statework_id, "godkiller.authority")
        advance("godkiller.diagnosed.partition.partitioned",
                ("godkiller.partition", "godkiller.baseline"))
        step_id = "godkiller.partitioned.authorize.extracting"
        fresh_kinds = ("godkiller.partition", "godkiller.baseline")
    elif statework_id == "testworks":
        advance("testworks.unassessed.inventory.inventoried", ("testworks.inventory",))
        stale_authority = _attest(authority, identity, statework_id, "testworks.authority")
        advance("testworks.inventoried.strategize.strategized",
                ("testworks.strategy", "testworks.risk_assessment"))
        step_id = "testworks.strategized.plan_run.executing"
        fresh_kinds = ("testworks.run_plan",)
    else:
        advance("terraformer.unassessed.validate_contracts.contracts_validated",
                ("terraformer.inventory", "terraformer.contract_validation"))
        stale_authority = _attest(authority, identity, statework_id, "terraformer.authority")
        advance("terraformer.contracts_validated.plan.composition_planned",
                ("terraformer.composition_plan", "terraformer.contract_validation"))
        step_id = "terraformer.composition_planned.authorize.connecting"
        fresh_kinds = ("terraformer.composition_plan",)

    stale_and_fresh = [stale_authority] + [
        _attest(authority, identity, statework_id, kind) for kind in fresh_kinds]
    rejected = authority.apply_step(
        identity, contract_hash=contract_hash, step_id=step_id,
        evidence_refs=stale_and_fresh, expected_revision=snapshot.revision)
    assert rejected.allowed is False
    assert rejected.reason == "evidence predates current state entry"
    assert authority.inspect_workflow(identity, contract_hash=contract_hash).revision == snapshot.revision

    fresh_kinds = (f"{statework_id}.authority", *fresh_kinds)
    decision, _refs, advanced = _apply(
        authority, identity, contract_hash, snapshot, step_id, fresh_kinds)
    assert decision.allowed
    assert advanced.current_state == {
        "godkiller": "EXTRACTING",
        "terraformer": "CONNECTING",
        "testworks": "EXECUTING",
    }[statework_id]


@pytest.mark.parametrize("statework_id", ["godkiller", "terraformer", "testworks"])
def test_adversarial_case_sets_keep_positive_and_negative_architecture_briefs(
        statework_id):
    path = ROOT / statework_id / "qualification" / "cases.yaml"
    cases = yaml.safe_load(path.read_text(encoding="utf-8"))["cases"]
    ids = {case["id"] for case in cases}
    assert SCENARIOS[statework_id]["positive"] <= ids
    assert SCENARIOS[statework_id]["negative"] <= ids
