from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from control_plane import EvidenceStore, SubjectStateStore, WorkflowAuthority
from selection_store import WorkflowSelectionStore
from transition_engine import TransitionEngine
from workflow_engines import (MilestoneWorkflowEngine, StateMachineWorkflowEngine,
                              WorkflowIdentity)


def _identity(statework_id: str, contract_version: str) -> WorkflowIdentity:
    return WorkflowIdentity(
        namespace_id="tenant-a", application_id="assistant",
        application_instance_id="assistant-1", workflow_id=statework_id,
        subject_ref=f"repo:{statework_id}", statework_id=statework_id,
        contract_version=contract_version)


def _evidence(evidence: EvidenceStore, *, ref: str, kind: str,
              subject_ref: str) -> None:
    evidence.create({
        "ref": ref,
        "kind": kind,
        "subject_ref": subject_ref,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "issuer": "host:test",
        "validator": f"test-{kind}-v1",
        "schema": f"test-{kind}-v1",
        "content_digest": f"digest:{ref}",
    })


def _authority(tmp_path: Path, evidence: EvidenceStore) -> WorkflowAuthority:
    return WorkflowAuthority(
        root=ROOT,
        state_store=SubjectStateStore(tmp_path / "subjects.json"),
        evidence_store=evidence,
        selection_store=WorkflowSelectionStore(tmp_path / "selections.json"),
    )


def test_state_machine_invalidated_fact_reopens_terminal_transition(tmp_path, monkeypatch):
    evidence = EvidenceStore()
    contract = {
        "initial_state": "OPEN",
        "states": ["OPEN", "DONE"],
        "completion_states": ["DONE"],
        "facts": {"approval_supported": {"terminal_required": True}},
        "transitions": [
            {
                "id": "fact.verify",
                "from": "OPEN",
                "to": "OPEN",
                "trigger": "verify",
                "required_evidence": ["review"],
                "work_class": "review",
                "domain_effect": "record_review",
                "progress_class": "LATERAL",
                "establishes_facts": ["approval_supported"],
            },
            {
                "id": "workflow.finish",
                "from": "OPEN",
                "to": "DONE",
                "trigger": "finish",
                "required_evidence": ["approval"],
                "work_class": "governance",
                "domain_effect": "finish_workflow",
                "progress_class": "TERMINAL",
                "requires_facts": ["approval_supported"],
            },
        ],
    }
    evidence_registry = {"kinds": {
        kind: {"allowed_issuers": ["host:test"],
               "validator": f"test-{kind}-v1", "schema": f"test-{kind}-v1"}
        for kind in ("review", "approval")}}
    engine = StateMachineWorkflowEngine(TransitionEngine(
        contract, evidence_registry=evidence_registry, require_registered=True,
        evidence_store=evidence))
    authority = _authority(tmp_path, evidence)
    contract_hash = "a" * 64
    monkeypatch.setattr(
        authority, "_bundle",
        lambda _statework_id, _contract_hash=None: (
            {}, contract, contract_hash, engine, evidence_registry))
    identity = _identity("fact-state-machine", engine.contract_version)
    _evidence(evidence, ref="review-v1", kind="review", subject_ref=identity.subject_ref)
    _evidence(evidence, ref="approval-v1", kind="approval", subject_ref=identity.subject_ref)

    opened = authority.inspect_workflow(identity, contract_hash=contract_hash)
    assert [step.step_id for step in opened.eligible_steps] == ["fact.verify"]
    verified = authority.apply_step(
        identity, contract_hash=contract_hash, step_id="fact.verify",
        evidence_refs=["review-v1"], expected_revision=opened.revision)
    assert verified.current_state == "OPEN"
    assert authority.state_store.get(identity.__dict__)["fact_ledger"][0]["status"] == "ESTABLISHED"

    ready = authority.inspect_workflow(identity, contract_hash=contract_hash)
    assert {step.step_id for step in ready.eligible_steps} == {
        "fact.verify", "workflow.finish"}
    finished = authority.apply_step(
        identity, contract_hash=contract_hash, step_id="workflow.finish",
        evidence_refs=["approval-v1"], expected_revision=ready.revision)
    assert finished.current_state == "DONE"
    assert finished.completed is True

    evidence.invalidate("review-v1")
    reopened = authority.inspect_workflow(identity, contract_hash=contract_hash)
    repeated = authority.inspect_workflow(identity, contract_hash=contract_hash)
    persisted = authority.state_store.get(identity.__dict__)
    history = authority.state_store.history_for(identity.__dict__)
    establishment_event = next(
        event for event in history
        if event["transition"].get("step_id") == "fact.verify")

    assert reopened.current_state == "OPEN"
    assert reopened.completed is False
    assert reopened.data["fact_ledger"][0]["status"] == "INVALIDATED"
    assert reopened.data["fact_ledger"][0]["invalidated_by"] == ["evidence:review-v1"]
    assert "workflow.finish" not in {step.step_id for step in reopened.eligible_steps}
    assert persisted["state"] == "OPEN"
    assert persisted["fact_ledger"] == list(reopened.data["fact_ledger"])
    assert establishment_event["transition"]["fact_effects"]["establishes_facts"] == [
        "approval_supported"]
    assert repeated.revision == reopened.revision
    assert repeated.current_state == "OPEN"


def test_milestone_invalidated_fact_reopens_completion_and_receipt_is_atomic(
        tmp_path, monkeypatch):
    evidence = EvidenceStore()
    contract = {
        "version": "1.0.0",
        "facts": {"migration_verified": {"terminal_required": True}},
        "steps": [
            {
                "id": "verify-migration",
                "required_evidence": ["verification"],
                "establishes_facts": ["migration_verified"],
            },
            {
                "id": "finalize-migration",
                "depends_on": ["verify-migration"],
                "required_evidence": ["approval"],
                "requires_facts": ["migration_verified"],
            },
        ],
    }
    engine = MilestoneWorkflowEngine()
    authority = _authority(tmp_path, evidence)
    contract_hash = "b" * 64
    monkeypatch.setattr(
        authority, "_bundle",
        lambda _statework_id, _contract_hash=None: (
            {}, contract, contract_hash, engine, {}))
    identity = _identity("fact-milestone", engine.contract_version)
    _evidence(evidence, ref="verification-v1", kind="verification",
              subject_ref=identity.subject_ref)
    _evidence(evidence, ref="approval-v1", kind="approval",
              subject_ref=identity.subject_ref)

    initial = authority.inspect_workflow(identity, contract_hash=contract_hash)
    assert [step.step_id for step in initial.eligible_steps] == ["verify-migration"]
    verified = authority.apply_step(
        identity, contract_hash=contract_hash, step_id="verify-migration",
        evidence_refs=["verification-v1"], expected_revision=initial.revision)
    record = authority.state_store.get(identity.__dict__)
    receipt = record["workflow_data"]["milestone_receipts"][0]
    history = authority.state_store.history_for(identity.__dict__)
    assert record["workflow_data"]["fact_ledger"][0]["status"] == "ESTABLISHED"
    assert receipt["establishes_facts"] == ["migration_verified"]
    assert history[-1]["transition"]["fact_effects"]["establishes_facts"] == [
        "migration_verified"]

    ready = authority.inspect_workflow(identity, contract_hash=contract_hash)
    assert {step.step_id for step in ready.eligible_steps} == {"finalize-migration"}
    finished = authority.apply_step(
        identity, contract_hash=contract_hash, step_id="finalize-migration",
        evidence_refs=["approval-v1"], expected_revision=ready.revision)
    assert finished.completed is True

    evidence.invalidate("verification-v1")
    reopened = authority.inspect_workflow(identity, contract_hash=contract_hash)
    repeated = authority.inspect_workflow(identity, contract_hash=contract_hash)
    record = authority.state_store.get(identity.__dict__)
    assert reopened.completed is False
    assert reopened.data["fact_ledger"][0]["status"] == "INVALIDATED"
    assert reopened.data["completed_steps"] == []
    assert [step.step_id for step in reopened.eligible_steps] == ["verify-migration"]
    assert record["workflow_data"]["fact_ledger"] == list(reopened.data["fact_ledger"])
    assert len(record["workflow_data"]["milestone_receipts"]) == 2
    assert repeated.revision == reopened.revision
