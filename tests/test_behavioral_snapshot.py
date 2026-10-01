from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from control_plane import (EvidenceStore, SubjectStateStore, TransitionError,
                           WorkflowAuthority)


def _authority(tmp_path: Path) -> WorkflowAuthority:
    return WorkflowAuthority(
        root=ROOT,
        state_store=SubjectStateStore(tmp_path / "subjects.json"),
        evidence_store=EvidenceStore(),
    )


def _active_gitter(authority: WorkflowAuthority) -> dict[str, object]:
    contract = authority.workflow_contract_identity("gitter")
    identity = {
        "namespace_id": "tenant-a",
        "application_id": "assistant",
        "application_instance_id": "assistant-1",
        "workflow_id": "repo-observation",
        "subject_ref": "repo:example",
        "statework_id": "gitter",
        "contract_version": contract["contract_version"],
    }
    return {"identity": identity, "contract_hash": contract["contract_hash"]}


def test_snapshot_returns_authoritative_state_and_only_compatible_candidates(tmp_path):
    authority = _authority(tmp_path)
    result = authority.behavioral_snapshot(
        active_workflows=[_active_gitter(authority)],
        candidate_statework_ids=["getter", "infrae", "tuid"],
    )

    assert len(result["snapshot_id"]) == 64
    assert result["active_workflows"][0]["current_state"] == "UNKNOWN"
    assert result["active_workflows"][0]["revision"] == 1
    assert result["active_workflows"][0]["eligible_steps"]
    options = {item["statework_id"]: item for item in result["eligible_stateworks"]}
    assert set(options) == {"getter", "infrae", "tuid"}
    assert "implementation" in options["getter"]["behavior_tags"]


def test_snapshot_never_accepts_unknown_or_unregistered_statework_candidates(tmp_path):
    authority = _authority(tmp_path)

    with pytest.raises(TransitionError, match="unavailable candidate"):
        authority.behavioral_snapshot(candidate_statework_ids=["agent-invented"])


def test_snapshot_rejects_a_stale_or_forged_contract_pin(tmp_path):
    authority = _authority(tmp_path)
    active = _active_gitter(authority)
    active["contract_hash"] = "0" * 64

    with pytest.raises(TransitionError, match="differs"):
        authority.behavioral_snapshot(active_workflows=[active])


def test_snapshot_applies_bounds_and_rejects_duplicate_active_stateworks(tmp_path):
    authority = _authority(tmp_path)
    active = _active_gitter(authority)

    with pytest.raises(TransitionError, match="must be unique"):
        authority.behavioral_snapshot(active_workflows=[active, active])
    with pytest.raises(TransitionError, match="exceeds its bounds"):
        authority.behavioral_snapshot(candidate_statework_ids=["tuid"] * 33)
