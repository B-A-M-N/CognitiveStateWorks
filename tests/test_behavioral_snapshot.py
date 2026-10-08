from __future__ import annotations

from pathlib import Path
import json
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from control_plane import (EvidenceStore, SubjectStateStore, TransitionError,
                           WorkflowAuthority, WorkflowSelectionStore)
from transition_engine import TransitionEngine
from workflow_engines import StateMachineWorkflowEngine, WorkflowIdentity


def _scope(suffix: str = "main") -> dict[str, str]:
    return {
        "namespace_id": "tenant-a",
        "application_id": "assistant",
        "application_instance_id": "assistant-1",
        "workflow_id": f"task-{suffix}",
        "subject_ref": "repo:example",
    }


def _authority(tmp_path: Path) -> WorkflowAuthority:
    return WorkflowAuthority(
        root=ROOT,
        state_store=SubjectStateStore(tmp_path / "subjects.json"),
        evidence_store=EvidenceStore(),
        selection_store=WorkflowSelectionStore(tmp_path / "selections.json"),
    )


def _identity(authority: WorkflowAuthority, scope, statework_id: str):
    contract = authority.workflow_contract_identity(statework_id)
    return ({**scope, "statework_id": statework_id,
             "contract_version": contract["contract_version"]}, contract)


def test_csw_owns_active_workflow_snapshot_and_eligible_choices(tmp_path):
    authority = _authority(tmp_path)
    scope = _scope()
    identity, contract = _identity(authority, scope, "gitter")
    selected = authority.activate_workflow(
        identity, contract_hash=contract["contract_hash"],
        expected_selection_revision=0)
    snapshot = authority.behavioral_snapshot(
        workflow_scope=scope, candidate_statework_ids=["getter", "infrae", "tuid"])

    assert selected["revision"] == 1
    assert len(snapshot["snapshot_id"]) == 64
    assert snapshot["selection_revision"] == 1
    assert snapshot["active_workflows"][0]["identity"]["statework_id"] == "gitter"
    assert snapshot["active_workflows"][0]["current_state"] == "UNKNOWN"
    assert snapshot["active_workflows"][0]["revision"] == 1
    assert snapshot["active_workflows"][0]["eligible_steps"]
    options = {item["statework_id"]: item for item in snapshot["eligible_stateworks"]}
    assert set(options) == {"getter", "infrae", "tuid"}
    assert "implementation" in options["getter"]["behavior_tags"]


def test_snapshot_cannot_be_forged_by_host_supplied_active_ids(tmp_path):
    authority = _authority(tmp_path)
    snapshot = authority.behavioral_snapshot(workflow_scope=_scope())

    assert snapshot["active_workflows"] == []
    assert {item["statework_id"] for item in snapshot["eligible_stateworks"]} == {
        "gitter", "infrae", "tuid"}


def test_rejected_transition_attempt_is_durable_and_does_not_advance_revision(tmp_path):
    authority = _authority(tmp_path)
    scope = _scope("transition-audit")
    identity, contract = _identity(authority, scope, "gitter")

    try:
        decision = authority.apply_step(
            identity, contract_hash=contract["contract_hash"],
            step_id="not-a-registered-step", evidence_refs=[],
            expected_revision=0)
    except TransitionError:
        decision = None
    assert decision is None or decision.allowed is False

    summary = authority.selection_store.transition_attempt_summary(scope)
    assert summary["schema_version"] == "csw-transition-attempts/v1"
    assert summary["status"] == "observed"
    assert summary["attempt_count"] == 1
    assert summary["accepted_count"] == 0
    assert summary["rejected_count"] == 1
    assert summary["pending_count"] == 0
    attempt = summary["attempts"][0]
    assert attempt["statework_id"] == "gitter"
    assert attempt["step_id"] == "not-a-registered-step"
    assert attempt["outcome"] == "rejected"
    assert attempt["before_revision"] == attempt["after_revision"]

    reopened = WorkflowSelectionStore(authority.selection_store.path)
    assert reopened.transition_attempt_summary(scope) == summary


def test_rejected_transition_attempt_is_durable_and_does_not_advance_revision(tmp_path):
    authority = _authority(tmp_path)
    scope = _scope("transition-audit")
    identity, contract = _identity(authority, scope, "gitter")

    try:
        decision = authority.apply_step(
            identity, contract_hash=contract["contract_hash"],
            step_id="not-a-registered-step", evidence_refs=[],
            expected_revision=0)
    except TransitionError:
        decision = None
    assert decision is None or decision.allowed is False

    summary = authority.selection_store.transition_attempt_summary(scope)
    assert summary["schema_version"] == "csw-transition-attempts/v1"
    assert summary["status"] == "observed"
    assert summary["attempt_count"] == 1
    assert summary["accepted_count"] == 0
    assert summary["rejected_count"] == 1
    assert summary["pending_count"] == 0
    attempt = summary["attempts"][0]
    assert attempt["statework_id"] == "gitter"
    assert attempt["step_id"] == "not-a-registered-step"
    assert attempt["outcome"] == "rejected"
    assert attempt["before_revision"] == attempt["after_revision"]

    reopened = WorkflowSelectionStore(authority.selection_store.path)
    assert reopened.transition_attempt_summary(scope) == summary


def test_active_snapshot_reports_evidence_supported_previous_and_legal_states(tmp_path):
    authority = _authority(tmp_path)
    scope = _scope("snapshot-semantics")
    contract = {
        "initial_state": "OPEN",
        "states": ["OPEN", "DONE"],
        "completion_states": ["DONE"],
        "transitions": [{
            "id": "snapshot.complete",
            "from": "OPEN",
            "to": "DONE",
            "trigger": "complete",
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
    engine = StateMachineWorkflowEngine(TransitionEngine(
        contract, evidence_registry=evidence_registry, require_registered=True,
        evidence_store=authority.evidence_store))
    contract_hash = "a" * 64
    statework_id = "snapshot-semantics"
    identity = WorkflowIdentity(
        namespace_id=scope["namespace_id"],
        application_id=scope["application_id"],
        application_instance_id=scope["application_instance_id"],
        workflow_id=scope["workflow_id"],
        subject_ref=scope["subject_ref"],
        statework_id=statework_id,
        contract_version=engine.contract_version,
    )
    authority._bundle = lambda _statework_id, _contract_hash=None: (
        {"id": statework_id, "composition": {"requires": []}},
        contract, contract_hash, engine, evidence_registry)
    compiled = dict(authority._compiled_registry)
    compiled["stateworks"] = [
        *compiled["stateworks"],
        {"id": statework_id,
         "manifest": {"id": statework_id, "composition": {"requires": []}}},
    ]
    authority._compiled_registry = compiled
    authority.activate_workflow(
        identity, contract_hash=contract_hash, expected_selection_revision=0)

    initial = authority.behavioral_snapshot(workflow_scope=scope)["active_workflows"][0]
    assert initial["previous_state"] is None
    assert initial["legal_next_states"] == ["DONE"]

    authority.evidence_store.create({
        "ref": "snapshot-approval-v1",
        "kind": "approval",
        "subject_ref": identity.subject_ref,
        "observed_at": "2025-01-01T00:00:00Z",
        "issuer": "host:test",
        "validator": "test-approval-v1",
        "schema": "test-approval-v1",
        "content_digest": "snapshot-approval-content-v1",
    })
    opened = authority.inspect_workflow(identity, contract_hash=contract_hash)
    authority.apply_step(
        identity, contract_hash=contract_hash, step_id="snapshot.complete",
        evidence_refs=["snapshot-approval-v1"], expected_revision=opened.revision)

    completed = authority.behavioral_snapshot(workflow_scope=scope)["active_workflows"][0]
    assert completed["current_state"] == "DONE"
    assert completed["previous_state"] == "OPEN"
    assert completed["legal_next_states"] == []

    authority.evidence_store.invalidate("snapshot-approval-v1")
    reopened = authority.behavioral_snapshot(workflow_scope=scope)["active_workflows"][0]
    assert reopened["current_state"] == "OPEN"
    assert reopened["previous_state"] is None
    assert reopened["legal_next_states"] == ["DONE"]


def test_milestone_completion_reopens_when_receipt_evidence_is_invalidated(tmp_path):
    from workflow_engines import MilestoneWorkflowEngine

    evidence = EvidenceStore()
    state_store = SubjectStateStore(tmp_path / "milestone-subjects.json")
    authority = WorkflowAuthority(
        root=ROOT, state_store=state_store, evidence_store=evidence,
        selection_store=WorkflowSelectionStore(tmp_path / "milestone-selections.json"))
    engine = MilestoneWorkflowEngine()
    contract = {"steps": [
        {"id": "design", "required_evidence": ["design_review"]},
        {"id": "build", "depends_on": ["design"],
         "required_evidence": ["build_receipt"]},
    ]}
    engine.validate_contract(contract)
    contract_hash = "a" * 64
    authority._bundle = lambda _statework_id, _contract_hash=None: (
        {}, contract, contract_hash, engine, {})
    identity = {
        **_scope("milestone-ledger"), "statework_id": "milestone-test",
        "contract_version": engine.contract_version,
    }

    def record(ref: str, kind: str) -> None:
        evidence.create({"ref": ref, "kind": kind,
                         "subject_ref": identity["subject_ref"]})

    record("design-evidence-v1", "design_review")
    record("build-evidence-v1", "build_receipt")
    first = authority.apply_step(
        identity, contract_hash=contract_hash, step_id="design",
        evidence_refs=["design-evidence-v1"], expected_revision=0)
    second = authority.apply_step(
        identity, contract_hash=contract_hash, step_id="build",
        evidence_refs=["build-evidence-v1"], expected_revision=first.revision)
    assert second.completed is True

    ledger = state_store.get(identity)["workflow_data"]
    assert "completed_steps" not in ledger
    assert len(ledger["milestone_receipts"]) == 2

    evidence.invalidate("design-evidence-v1")
    reopened = authority.inspect_workflow(identity, contract_hash=contract_hash)
    assert reopened.completed is False
    assert [step.step_id for step in reopened.eligible_steps] == ["design"]

    record("design-evidence-v2", "design_review")
    repaired = authority.apply_step(
        identity, contract_hash=contract_hash, step_id="design",
        evidence_refs=["design-evidence-v2"], expected_revision=reopened.revision)
    assert repaired.completed is True


def test_authority_pins_compiled_registry_until_explicit_reload(tmp_path, monkeypatch):
    import workflow_authority

    original = workflow_authority.load_compiled_registry
    loads = []

    def counted(root=None, *, verify_bundles=True):
        loads.append(root)
        return original(root, verify_bundles=verify_bundles)

    monkeypatch.setattr(workflow_authority, "load_compiled_registry", counted)
    authority = _authority(tmp_path)
    pinned_hash = authority.registry_hash
    for _ in range(20):
        authority.behavioral_snapshot(workflow_scope=_scope())
        authority.workflow_contract_identity("gitter")
    assert len(loads) == 1
    assert authority.reload_registry(expected_registry_hash=pinned_hash) == pinned_hash
    assert len(loads) == 2
    with pytest.raises(TransitionError, match="does not match"):
        authority.reload_registry(expected_registry_hash="0" * 64)
    assert authority.registry_hash == pinned_hash


def test_active_bundle_contracts_are_read_once_across_repeated_snapshots(
        tmp_path, monkeypatch):
    import workflow_authority

    authority = _authority(tmp_path)
    scope = _scope("bundle-cache")
    original = workflow_authority._load_yaml
    reads = []

    def counted(path):
        reads.append(Path(path))
        return original(path)

    monkeypatch.setattr(workflow_authority, "_load_yaml", counted)
    gitter, gitter_contract = _identity(authority, scope, "gitter")
    selected = authority.activate_workflow(
        gitter, contract_hash=gitter_contract["contract_hash"],
        expected_selection_revision=0)
    getter, getter_contract = _identity(authority, scope, "getter")
    selected = authority.activate_workflow(
        getter, contract_hash=getter_contract["contract_hash"],
        expected_selection_revision=selected["revision"])

    assert len(reads) == 2
    pinned_read_count = len(reads)
    for _ in range(100):
        snapshot = authority.behavioral_snapshot(workflow_scope=scope)
        assert len(snapshot["active_workflows"]) == 2
    assert len(reads) == pinned_read_count

    registry_hash = authority.registry_hash
    authority.reload_registry(expected_registry_hash=registry_hash)
    authority.behavioral_snapshot(workflow_scope=scope)
    assert len(reads) == pinned_read_count + 2
    for _ in range(10):
        authority.behavioral_snapshot(workflow_scope=scope)
    assert len(reads) == pinned_read_count + 2


def test_csw_rejects_unknown_or_composition_ineligible_activation(tmp_path):
    authority = _authority(tmp_path)
    scope = _scope()
    getter_identity, getter_contract = _identity(authority, scope, "getter")

    with pytest.raises(TransitionError, match="composition-compatible"):
        authority.activate_workflow(
            getter_identity, contract_hash=getter_contract["contract_hash"],
            expected_selection_revision=0)
    with pytest.raises(TransitionError, match="unavailable candidate"):
        authority.behavioral_snapshot(
            workflow_scope=scope, candidate_statework_ids=["agent-invented"])


def test_activation_rejects_stale_contract_pin_and_selection_revision(tmp_path):
    authority = _authority(tmp_path)
    scope = _scope()
    identity, contract = _identity(authority, scope, "gitter")

    with pytest.raises(TransitionError, match="differs"):
        authority.activate_workflow(
            identity, contract_hash="0" * 64, expected_selection_revision=0)
    selected = authority.activate_workflow(
        identity, contract_hash=contract["contract_hash"],
        expected_selection_revision=0)
    with pytest.raises(TransitionError, match="selection revision conflict"):
        authority.activate_workflow(
            identity, contract_hash=contract["contract_hash"],
            expected_selection_revision=0)
    assert selected["revision"] == 1


def test_required_workflow_cannot_be_deactivated_while_dependent_is_active(tmp_path):
    authority = _authority(tmp_path)
    scope = _scope()
    gitter, gitter_contract = _identity(authority, scope, "gitter")
    selected = authority.activate_workflow(
        gitter, contract_hash=gitter_contract["contract_hash"],
        expected_selection_revision=0)
    getter, getter_contract = _identity(authority, scope, "getter")
    selected = authority.activate_workflow(
        getter, contract_hash=getter_contract["contract_hash"],
        expected_selection_revision=selected["revision"])

    retained = authority.deactivate_workflow(
        workflow_scope=scope, statework_id="gitter",
        expected_selection_revision=selected["revision"],
        expected_activation_owner="host")
    assert retained["disposition"] == "retained_required"
    assert retained["required_by"] == ["getter"]
    assert retained["active_workflows"]["gitter"]["activation_owner"] == "dependency"


def test_dp_release_cannot_remove_an_independently_activated_workflow(tmp_path):
    authority = _authority(tmp_path)
    scope = _scope()
    identity, contract = _identity(authority, scope, "gitter")
    selected = authority.activate_workflow(
        identity, contract_hash=contract["contract_hash"],
        expected_selection_revision=0)

    mismatch = authority.deactivate_workflow(
        workflow_scope=scope, statework_id="gitter",
        expected_selection_revision=selected["revision"],
        expected_activation_owner="digitalpsychology",
        expected_control_session_id="dp-session-1",
        expected_intervention_id="intervention-1")
    assert mismatch["disposition"] == "owner_mismatch"

    with pytest.raises(TransitionError, match="requires an activation owner"):
        authority.deactivate_workflow(
            workflow_scope=scope, statework_id="gitter",
            expected_selection_revision=selected["revision"])

    snapshot = authority.behavioral_snapshot(workflow_scope=scope)
    assert snapshot["active_workflows"][0]["identity"]["statework_id"] == "gitter"

    released = authority.deactivate_workflow(
        workflow_scope=scope, statework_id="gitter",
        expected_selection_revision=selected["revision"],
        expected_activation_owner="host")
    assert released["active_workflows"] == {}


def test_dp_owner_can_release_only_its_matching_temporary_activation(tmp_path):
    authority = _authority(tmp_path)
    scope = _scope()
    identity, contract = _identity(authority, scope, "gitter")
    selected = authority.activate_workflow(
        identity, contract_hash=contract["contract_hash"],
        expected_selection_revision=0,
        activation_owner="digitalpsychology",
        control_session_id="dp-session-1",
        intervention_id="intervention-1",
        expires_at_action=5)

    mismatch = authority.deactivate_workflow(
        workflow_scope=scope, statework_id="gitter",
        expected_selection_revision=selected["revision"],
        expected_activation_owner="digitalpsychology",
        expected_control_session_id="unrelated-session",
        expected_intervention_id="intervention-1")
    assert mismatch["disposition"] == "owner_mismatch"

    released = authority.deactivate_workflow(
        workflow_scope=scope, statework_id="gitter",
        expected_selection_revision=selected["revision"],
        expected_activation_owner="digitalpsychology",
        expected_control_session_id="dp-session-1",
        expected_intervention_id="intervention-1")
    assert released["revision"] == selected["revision"] + 1
    assert released["active_workflows"] == {}


def test_dp_activation_has_session_scoped_expiring_provenance(tmp_path):
    authority = _authority(tmp_path)
    scope = _scope()
    identity, contract = _identity(authority, scope, "gitter")
    assert authority.workflow_activation_metadata(
        workflow_scope=scope, statework_id="gitter") is None
    selected = authority.activate_workflow(
        identity, contract_hash=contract["contract_hash"],
        expected_selection_revision=0,
        activation_owner="digitalpsychology",
        control_session_id="dp-session-1",
        intervention_id="intervention-1",
        expires_at_action=2)

    row = selected["active_workflows"]["gitter"]
    assert row["activation_owner"] == "digitalpsychology"
    assert row["control_session_id"] == "dp-session-1"
    assert row["intervention_id"] == "intervention-1"
    assert row["activation_revision"] == selected["revision"] == 1
    assert authority.workflow_activation_metadata(
        workflow_scope=scope, statework_id="gitter") == {
            "activation_owner": "digitalpsychology",
            "control_session_id": "dp-session-1",
            "intervention_id": "intervention-1",
            "activation_revision": 1,
            "expires_at_action": 2,
        }

    wrong_intervention = authority.deactivate_workflow(
        workflow_scope=scope, statework_id="gitter",
        expected_selection_revision=selected["revision"],
        expected_activation_owner="digitalpsychology",
        expected_control_session_id="dp-session-1",
        expected_intervention_id="another-intervention")
    assert wrong_intervention["disposition"] == "owner_mismatch"
    wrong_session = authority.deactivate_workflow(
        workflow_scope=scope, statework_id="gitter",
        expected_selection_revision=selected["revision"],
        expected_activation_owner="digitalpsychology",
        expected_control_session_id="dp-session-1",
        expected_intervention_id="another-session")
    assert wrong_session["disposition"] == "owner_mismatch"

    still_active = authority.behavioral_snapshot(workflow_scope=scope)
    assert still_active["active_workflows"][0]["identity"]["statework_id"] == "gitter"
    assert still_active["selection_revision"] == selected["revision"]

    # Shared lease-boundary convention: expires_at_action = 1 is effective
    # through action 1 and released once the index reaches 2. CSW and CFW must
    # release on the same action.
    unchanged = authority.expire_workflow_leases(
        workflow_scope=scope, host_action_index=1)
    assert unchanged["revision"] == selected["revision"]
    before_expiry = authority.behavioral_snapshot(workflow_scope=scope)
    assert before_expiry["active_workflows"]

    # expires_at_action = 2 is effective through action 2 and released at 3.
    still_held = authority.expire_workflow_leases(
        workflow_scope=scope, host_action_index=2)
    assert still_held["revision"] == selected["revision"]
    assert still_held["active_workflows"]

    expired_selection = authority.expire_workflow_leases(
        workflow_scope=scope, host_action_index=3)
    assert expired_selection["revision"] == selected["revision"] + 1
    assert expired_selection["active_workflows"] == {}
    expired = authority.behavioral_snapshot(workflow_scope=scope)
    assert expired["active_workflows"] == []


def test_expired_dp_dependency_lease_is_retained_and_later_released(tmp_path):
    authority = _authority(tmp_path)
    scope = _scope("dependency-retention")
    required_identity, required_contract = _identity(authority, scope, "gitter")
    selected = authority.activate_workflow(
        required_identity, contract_hash=required_contract["contract_hash"],
        expected_selection_revision=0, activation_owner="digitalpsychology",
        control_session_id="dp-session-1", intervention_id="intervention-gitter",
        expires_at_action=1)
    consumer_identity, consumer_contract = _identity(authority, scope, "getter")
    selected = authority.activate_workflow(
        consumer_identity, contract_hash=consumer_contract["contract_hash"],
        expected_selection_revision=selected["revision"],
        activation_owner="digitalpsychology", control_session_id="dp-session-1",
        intervention_id="intervention-getter", expires_at_action=5)

    expired = authority.expire_workflow_leases(
        workflow_scope=scope, host_action_index=2)
    assert set(expired["active_workflows"]) == {"gitter", "getter"}
    metadata = authority.workflow_activation_metadata(
        workflow_scope=scope, statework_id="gitter")
    assert metadata["activation_owner"] == "dependency"
    assert metadata["control_session_id"] is None
    assert metadata["intervention_id"] is None
    assert metadata["expires_at_action"] is None
    assert metadata["required_by"] == ["getter"]

    retained = authority.deactivate_workflow(
        workflow_scope=scope, statework_id="gitter",
        expected_selection_revision=expired["revision"],
        expected_activation_owner="digitalpsychology",
        expected_control_session_id="dp-session-1",
        expected_intervention_id="intervention-gitter")
    assert retained["disposition"] == "retained_required"
    assert retained["required_by"] == ["getter"]
    assert retained["revision"] == expired["revision"]

    released = authority.deactivate_workflow(
        workflow_scope=scope, statework_id="getter",
        expected_selection_revision=retained["revision"],
        expected_activation_owner="digitalpsychology",
        expected_control_session_id="dp-session-1",
        expected_intervention_id="intervention-getter")
    assert released["disposition"] == "released"
    assert set(released["released_stateworks"]) == {"gitter", "getter"}
    assert released["active_workflows"] == {}


def test_releasing_last_consumer_cascades_real_three_level_dependency_chain(tmp_path):
    authority = _authority(tmp_path)
    scope = _scope("three-level-cascade")
    authority._compiled_registry = {
        "registry_hash": authority.registry_hash,
        "stateworks": [
            {"id": "A", "manifest": {"id": "A", "composition": {"requires": []}}},
            {"id": "B", "manifest": {"id": "B", "composition": {"requires": ["A"]}}},
            {"id": "C", "manifest": {"id": "C", "composition": {"requires": ["B"]}}},
        ],
    }
    rows = {
        "A": {"identity": {"statework_id": "A"}, "contract_hash": "a" * 64,
              "activation_owner": "dependency", "control_session_id": None,
              "intervention_id": None, "activation_revision": 1,
              "expires_at_action": None},
        "B": {"identity": {"statework_id": "B"}, "contract_hash": "b" * 64,
              "activation_owner": "dependency", "control_session_id": None,
              "intervention_id": None, "activation_revision": 1,
              "expires_at_action": None},
        "C": {"identity": {"statework_id": "C"}, "contract_hash": "c" * 64,
              "activation_owner": "digitalpsychology",
              "control_session_id": "dp-session", "intervention_id": "release-C",
              "activation_revision": 1, "expires_at_action": 9},
    }
    selected = authority.selection_store.replace(
        scope, expected_revision=0, active_workflows=rows)

    released = authority.deactivate_workflow(
        workflow_scope=scope, statework_id="C",
        expected_selection_revision=selected["revision"],
        expected_activation_owner="digitalpsychology",
        expected_control_session_id="dp-session",
        expected_intervention_id="release-C")

    assert released["disposition"] == "released"
    assert released["released_stateworks"] == ["A", "B", "C"]
    assert released["active_workflows"] == {}
    assert released["revision"] == selected["revision"] + 1

def test_expiring_dp_workflow_preserves_an_independent_host_workflow(tmp_path):
    authority = _authority(tmp_path)
    scope = _scope("partial-expiry")
    dp_identity, dp_contract = _identity(authority, scope, "infrae")
    selected = authority.activate_workflow(
        dp_identity, contract_hash=dp_contract["contract_hash"],
        expected_selection_revision=0,
        activation_owner="digitalpsychology", control_session_id="dp-session-a",
        intervention_id="dp-intervention-a", expires_at_action=2)
    host_identity, host_contract = _identity(authority, scope, "tuid")
    selected = authority.activate_workflow(
        host_identity, contract_hash=host_contract["contract_hash"],
        expected_selection_revision=selected["revision"],
        activation_owner="host")

    # Under the shared lease-boundary convention a lease with
    # expires_at_action = 2 is still effective at action 2 and is released
    # once the index reaches 3.
    expired = authority.expire_workflow_leases(
        workflow_scope=scope, host_action_index=3)

    assert set(expired["active_workflows"]) == {"tuid"}
    assert expired["active_workflows"]["tuid"]["activation_owner"] == "host"


def test_legacy_selection_rows_remain_permanent_host_activations(tmp_path):
    authority = _authority(tmp_path / "contract-source")
    scope = _scope()
    identity, contract = _identity(authority, scope, "gitter")
    selection_path = tmp_path / "selections.json"
    scope_key = json.dumps(scope, sort_keys=True, separators=(",", ":"))
    selection_path.write_text(json.dumps({
        "version": 1,
        "scopes": {scope_key: {
            "scope": scope, "revision": 1,
            "active_workflows": {"gitter": {
                "identity": identity, "contract_hash": contract["contract_hash"]}}
        }},
    }), encoding="utf-8")

    authority = WorkflowAuthority(
        root=ROOT, state_store=SubjectStateStore(tmp_path / "subjects.json"),
        evidence_store=EvidenceStore(),
        selection_store=WorkflowSelectionStore(selection_path))

    snapshot = authority.behavioral_snapshot(workflow_scope=scope)
    assert snapshot["active_workflows"][0]["identity"]["statework_id"] == "gitter"


def test_sqlite_selection_store_persists_scoped_compare_and_swap(tmp_path):
    first = WorkflowSelectionStore(tmp_path / "selections.json")
    scope = _scope("sqlite")
    assert first.get(scope)["revision"] == 0
    updated = first.replace(scope, expected_revision=0, active_workflows={})
    assert updated["revision"] == 1
    second = WorkflowSelectionStore(tmp_path / "selections.json")
    assert second.get(scope)["revision"] == 1
    with pytest.raises(TransitionError, match="revision conflict"):
        first.replace(scope, expected_revision=0, active_workflows={})
    assert (tmp_path / "selections.sqlite3").is_file()
