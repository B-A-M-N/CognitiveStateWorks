from __future__ import annotations

from pathlib import Path
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

    with pytest.raises(TransitionError, match="required by active"):
        authority.deactivate_workflow(
            workflow_scope=scope, statework_id="gitter",
            expected_selection_revision=selected["revision"])
