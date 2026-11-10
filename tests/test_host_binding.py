from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from control_plane import (EvidenceStore, SubjectStateStore, WorkflowAuthority,
                           WorkflowSelectionStore)
from host_binding import CSWWorkflowBinding, resolve_bindings


def _scope(subject_ref: str = "repo:host-binding") -> dict[str, str]:
    return {
        "namespace_id": "tenant-a",
        "application_id": "assistant",
        "application_instance_id": "assistant-1",
        "workflow_id": "task-host-binding",
        "subject_ref": subject_ref,
    }


def _authority(tmp_path: Path) -> WorkflowAuthority:
    return WorkflowAuthority(
        root=ROOT,
        state_store=SubjectStateStore(tmp_path / "subjects.json"),
        evidence_store=EvidenceStore(),
        selection_store=WorkflowSelectionStore(tmp_path / "selections.json"),
    )


def test_host_binding_returns_registered_scope_bound_compatible_workflows(tmp_path):
    authority = _authority(tmp_path)
    scope = _scope()
    candidates = ["gitter", "getter", "infrae", "tuid"]

    bindings = resolve_bindings(
        authority, scope, {"candidate_statework_ids": candidates})
    by_id = {binding.identity["statework_id"]: binding for binding in bindings}

    # getter requires gitter and is not offered until CSW records that premise.
    assert set(by_id) == {"gitter", "infrae", "tuid"}
    for binding in bindings:
        assert isinstance(binding, CSWWorkflowBinding)
        assert {name: binding.identity[name] for name in scope} == scope
        assert len(binding.contract_hash) == 64

    gitter_contract = authority.workflow_contract_identity("gitter")
    authority.activate_workflow(
        {**scope, "statework_id": "gitter",
         "contract_version": gitter_contract["contract_version"]},
        contract_hash=gitter_contract["contract_hash"],
        expected_selection_revision=0)
    bindings = resolve_bindings(
        authority, scope, {"candidate_statework_ids": candidates})
    assert {item.identity["statework_id"] for item in bindings} == set(candidates)


def test_host_binding_filters_task_candidates_but_keeps_scoped_active_workflows(tmp_path):
    authority = _authority(tmp_path)
    scope = _scope()
    contract = authority.workflow_contract_identity("gitter")
    authority.activate_workflow(
        {**scope, "statework_id": "gitter",
         "contract_version": contract["contract_version"]},
        contract_hash=contract["contract_hash"], expected_selection_revision=0)

    bindings = resolve_bindings(
        authority, scope, {"behavior_tags": ["implementation"]})
    assert {item.identity["statework_id"] for item in bindings} == {
        "gitter", "getter", "tuid", "godkiller", "terraformer"}

    other_scope = _scope("repo:other")
    other_bindings = resolve_bindings(
        authority, other_scope, {"candidate_statework_ids": ["gitter"]})
    assert {item.identity["statework_id"] for item in other_bindings} == {"gitter"}
    assert all(item.identity["subject_ref"] == other_scope["subject_ref"]
               for item in other_bindings)


def test_host_binding_rejects_unknown_statework_and_scope_overrides(tmp_path):
    authority = _authority(tmp_path)
    try:
        resolve_bindings(
            authority, _scope(), {"candidate_statework_ids": ["model-invented"]})
    except ValueError as exc:
        assert "unregistered" in str(exc)
    else:
        raise AssertionError("host binding accepted an unregistered StateWork")

    try:
        resolve_bindings(authority, _scope(), {"subject_ref": "repo:other"})
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("task context overrode the runtime identity scope")
