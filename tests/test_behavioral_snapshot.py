from __future__ import annotations

from pathlib import Path
import json
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from control_plane import (EvidenceStore, SubjectStateStore, TransitionError,
                           WorkflowAuthority, WorkflowSelectionStore)


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
