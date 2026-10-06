from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from state_store import PacketStore, SubjectStateStore
from selection_store import WorkflowSelectionStore


SCOPE = {
    "namespace_id": "tenant-a", "application_id": "app",
    "application_instance_id": "app-1", "workflow_id": "task",
    "subject_ref": "repo:example",
}


@pytest.mark.parametrize("suffix", [".sqlite3", ".db"])
def test_fresh_sqlite_selection_and_subject_paths_are_not_legacy_json(
        tmp_path: Path, suffix: str):
    selection = WorkflowSelectionStore(tmp_path / f"selection{suffix}")
    subject = SubjectStateStore(tmp_path / f"subject{suffix}")
    assert selection.legacy_path is None
    assert subject.legacy_path is None
    assert selection.get(SCOPE)["active_workflows"] == {}
    assert subject.get({**SCOPE, "statework_id": "gitter",
                        "contract_version": "1.0.0"})["revision"] == 0


@pytest.mark.parametrize("suffix", [".sqlite3", ".db"])
def test_fresh_sqlite_packet_path_is_not_legacy_json(tmp_path: Path, suffix: str):
    store = PacketStore(storage_path=tmp_path / f"packets{suffix}")
    assert store.legacy_storage_path is None
    assert store.revision == 0


def test_json_legacy_migration_and_reopen_for_all_stores(tmp_path: Path):
    selection_json = tmp_path / "selection.json"
    selection_json.write_text(json.dumps({"version": 2, "scopes": {}}), encoding="utf-8")
    subject_json = tmp_path / "subject.json"
    subject_json.write_text(json.dumps({"version": 1, "subjects": {}, "history": []}),
                            encoding="utf-8")
    packet_json = tmp_path / "packets.json"
    packet_json.write_text(json.dumps({"revision": 0, "packets": []}), encoding="utf-8")

    selection = WorkflowSelectionStore(selection_json)
    subject = SubjectStateStore(subject_json)
    packets = PacketStore(storage_path=packet_json)
    database_paths = (selection_json.with_suffix(".sqlite3"),
                      subject_json.with_suffix(".sqlite3"),
                      packet_json.with_suffix(".sqlite3"))
    assert all(path.is_file() for path in database_paths)

    assert WorkflowSelectionStore(database_paths[0]).get(SCOPE)["revision"] == 0
    assert SubjectStateStore(database_paths[1]).get({
        **SCOPE, "statework_id": "gitter", "contract_version": "1.0.0"})["revision"] == 0
    assert PacketStore(storage_path=database_paths[2]).revision == 0


def test_selection_checkpoint_restores_exact_ownership_rows_with_cas(tmp_path: Path):
    store = WorkflowSelectionStore(tmp_path / "selection.sqlite3")
    rows = {
        "prerequisite": {
            "identity": {"statework_id": "prerequisite"}, "contract_hash": "a" * 64,
            "activation_owner": "dependency", "control_session_id": None,
            "intervention_id": None, "activation_revision": 1,
            "expires_at_action": None,
        },
        "dependent": {
            "identity": {"statework_id": "dependent"}, "contract_hash": "b" * 64,
            "activation_owner": "digitalpsychology", "control_session_id": "dp-session",
            "intervention_id": "intervention", "activation_revision": 1,
            "expires_at_action": 7,
        },
    }
    original = store.replace(SCOPE, expected_revision=0, active_workflows=rows)
    store.create_checkpoint(SCOPE, tick_id="cascade-release", expected_revision=1)
    released = store.replace(SCOPE, expected_revision=1, active_workflows={})

    restored = store.restore_checkpoint(
        SCOPE, tick_id="cascade-release", expected_revision=released["revision"])

    assert restored is not None
    assert restored["active_workflows"] == original["active_workflows"]
    assert restored["revision"] == released["revision"] + 1
    assert store.restore_checkpoint(
        SCOPE, tick_id="cascade-release", expected_revision=restored["revision"]) is None
