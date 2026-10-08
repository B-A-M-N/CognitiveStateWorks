from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from control_plane import EvidenceStore, SubjectStateStore, WorkflowAuthority
from errors import TransitionError
from selection_store import WorkflowSelectionStore
from transition_engine import TransitionEngine
from workflow_engines import StateMachineWorkflowEngine, WorkflowIdentity


def test_state_machine_completion_reopens_after_supporting_evidence_invalidation(
        tmp_path, monkeypatch):
    evidence = EvidenceStore()
    contract = {
        "initial_state": "OPEN",
        "states": ["OPEN", "DONE"],
        "completion_states": ["DONE"],
        "transitions": [{
            "id": "completion.approve",
            "from": "OPEN",
            "to": "DONE",
            "trigger": "approve",
            "required_evidence": ["approval"],
            "work_class": "governance",
            "domain_effect": "complete_task",
            "progress_class": "TERMINAL",
            "consequential": True,
        }],
    }
    evidence_registry = {"kinds": {"approval": {
        "allowed_issuers": ["host:test"],
        "validator": "test-approval-v1",
        "schema": "test-approval-v1",
    }}}
    transition_engine = TransitionEngine(
        contract, evidence_registry=evidence_registry, require_registered=True,
        evidence_store=evidence)
    engine = StateMachineWorkflowEngine(transition_engine)
    authority = WorkflowAuthority(
        root=ROOT,
        state_store=SubjectStateStore(tmp_path / "subjects.json"),
        evidence_store=evidence,
        selection_store=WorkflowSelectionStore(tmp_path / "selections.json"),
    )
    contract_hash = "a" * 64
    monkeypatch.setattr(
        authority, "_bundle",
        lambda _statework_id, _contract_hash=None: (
            {}, contract, contract_hash, engine, evidence_registry))
    identity = WorkflowIdentity(
        namespace_id="tenant-a",
        application_id="assistant",
        application_instance_id="assistant-1",
        workflow_id="task-completion",
        subject_ref="repo:example",
        statework_id="completion-test",
        contract_version=engine.contract_version,
    )

    evidence.create({
        "ref": "approval-evidence-v1",
        "kind": "approval",
        "subject_ref": identity.subject_ref,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "issuer": "host:test",
        "validator": "test-approval-v1",
        "schema": "test-approval-v1",
        "content_digest": "approval-content-v1",
    })

    opened = authority.inspect_workflow(identity, contract_hash=contract_hash)
    completed = authority.apply_step(
        identity, contract_hash=contract_hash, step_id="completion.approve",
        evidence_refs=["approval-evidence-v1"], expected_revision=opened.revision)
    assert completed.completed is True
    assert completed.current_state == "DONE"
    transition_scope = {name: getattr(identity, name)
                        for name in WorkflowSelectionStore.SCOPE_FIELDS}
    transition_audit = authority.selection_store.transition_attempt_summary(
        transition_scope)
    assert transition_audit["accepted_count"] == 1
    assert transition_audit["rejected_count"] == 0
    assert transition_audit["attempts"][0]["outcome"] == "accepted"
    assert transition_audit["attempts"][0]["after_revision"] == \
        transition_audit["attempts"][0]["before_revision"] + 1

    evidence.invalidate("approval-evidence-v1")
    reopened = authority.inspect_workflow(identity, contract_hash=contract_hash)
    repeated = authority.inspect_workflow(identity, contract_hash=contract_hash)

    assert reopened.current_state == "OPEN"
    assert reopened.completed is False
    assert [step.step_id for step in reopened.eligible_steps] == ["completion.approve"]
    assert repeated.current_state == "OPEN"
    assert repeated.revision == reopened.revision
    assert authority.state_store.get(identity.__dict__)["state"] == "OPEN"
    history = authority.state_store.history_for(identity.__dict__)
    assert len(history) == reopened.revision
    assert all(isinstance(event, dict) for event in history)
    with pytest.raises(TransitionError, match="inspection bound"):
        authority.state_store.history_for(identity.__dict__, maximum=1)


def test_durable_invalidation_reopens_only_dependent_fact_after_authority_restart(
        tmp_path, monkeypatch):
    evidence_path = tmp_path / "evidence.json"
    state_path = tmp_path / "subjects.json"
    selection_path = tmp_path / "selections.json"
    evidence = EvidenceStore()
    contract = {
        "initial_state": "OPEN",
        "states": ["OPEN", "DONE"],
        "completion_states": ["DONE"],
        "facts": {
            "review_supported": {"terminal_required": True},
            "independent_baseline_preserved": {},
        },
        "transitions": [
            {
                "id": "verify-review",
                "from": "OPEN",
                "to": "OPEN",
                "trigger": "verify_review",
                "required_evidence": ["review"],
                "work_class": "review",
                "domain_effect": "record_review",
                "progress_class": "LATERAL",
                "establishes_facts": ["review_supported"],
            },
            {
                "id": "verify-baseline",
                "from": "OPEN",
                "to": "OPEN",
                "trigger": "verify_baseline",
                "required_evidence": ["baseline"],
                "work_class": "validation",
                "domain_effect": "record_baseline",
                "progress_class": "LATERAL",
                "establishes_facts": ["independent_baseline_preserved"],
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
                "requires_facts": ["review_supported"],
            },
        ],
    }
    evidence_registry = {"kinds": {
        kind: {"allowed_issuers": ["host:test"],
               "validator": f"test-{kind}-v1", "schema": f"test-{kind}-v1"}
        for kind in ("review", "baseline", "approval")}}
    contract_hash = "c" * 64
    identity = WorkflowIdentity(
        namespace_id="tenant-a", application_id="assistant",
        application_instance_id="assistant-1", workflow_id="restart-test",
        subject_ref="repo:restart-test", statework_id="restart-fact-test",
        contract_version="1.0.0")

    def make_authority(store: EvidenceStore) -> WorkflowAuthority:
        authority = WorkflowAuthority(
            root=ROOT,
            state_store=SubjectStateStore(state_path),
            evidence_store=store,
            selection_store=WorkflowSelectionStore(selection_path),
            storage_identity={
                "state_store": str(state_path.resolve()),
                "selection_store": str(selection_path.resolve()),
                "evidence_store": str(evidence_path.resolve()),
            },
        )
        engine = StateMachineWorkflowEngine(TransitionEngine(
            contract, evidence_registry=evidence_registry, require_registered=True,
            evidence_store=store))
        monkeypatch.setattr(
            authority, "_bundle",
            lambda _statework_id, _contract_hash=None: (
                {}, contract, contract_hash, engine, evidence_registry))
        return authority

    for ref, kind in (("review-v1", "review"),
                      ("baseline-v1", "baseline"),
                      ("approval-v1", "approval")):
        evidence.create({
            "ref": ref,
            "kind": kind,
            "subject_ref": identity.subject_ref,
            "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "issuer": "host:test",
            "validator": f"test-{kind}-v1",
            "schema": f"test-{kind}-v1",
            "content_digest": f"digest:{ref}",
        })
    evidence.save(evidence_path)

    authority = make_authority(evidence)
    snapshot = authority.inspect_workflow(identity, contract_hash=contract_hash)
    for step_id, ref in (("verify-review", "review-v1"),
                         ("verify-baseline", "baseline-v1"),
                         ("workflow.finish", "approval-v1")):
        decision = authority.apply_step(
            identity, contract_hash=contract_hash, step_id=step_id,
            evidence_refs=[ref], expected_revision=snapshot.revision)
        snapshot = authority.inspect_workflow(identity, contract_hash=contract_hash)
    assert snapshot.completed is True
    assert {item["fact_id"]: item["status"] for item in
            snapshot.data["fact_ledger"]} == {
                "independent_baseline_preserved": "ESTABLISHED",
                "review_supported": "ESTABLISHED",
            }

    evidence.invalidate("review-v1")
    evidence.save(evidence_path)

    # A fresh authority has no in-memory evidence. Inspection must reload the
    # attested durable store, replay the workflow history, and correct state.
    restarted = make_authority(EvidenceStore())
    reopened = restarted.inspect_workflow(identity, contract_hash=contract_hash)
    persisted = restarted.state_store.get(identity.__dict__)
    statuses = {item["fact_id"]: item["status"]
                for item in reopened.data["fact_ledger"]}

    assert reopened.current_state == "OPEN"
    assert reopened.completed is False
    assert statuses == {
        "independent_baseline_preserved": "ESTABLISHED",
        "review_supported": "INVALIDATED",
    }
    assert "workflow.finish" not in {
        step.step_id for step in reopened.eligible_steps}
    assert persisted["state"] == "OPEN"
    assert {item["fact_id"]: item["status"]
            for item in persisted["fact_ledger"]} == statuses
    persisted_evidence = json.loads(evidence_path.read_text())
    invalidated = next(item for item in persisted_evidence
                       if item["ref"] == "review-v1")
    assert invalidated["invalidated"] is True
