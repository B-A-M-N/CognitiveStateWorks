from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evidence import EvidenceStore
from state_store import SubjectStateStore
from workflow_controller import StandaloneStateWorkController


def _edge(origin: str, destination: str, trigger: str) -> dict:
    return {
        "id": f"test.{origin.lower()}.{trigger}.{destination.lower()}",
        "from": origin,
        "to": destination,
        "trigger": trigger,
        "required_evidence": ["authority"],
        "work_class": "test",
        "domain_effect": f"enter_{destination.lower()}",
        "progress_class": "FORWARD_PROGRESS",
        "consequential": True,
        "evidence_freshness": {"mode": "after_state_entry"},
    }


def _evidence(evidence: EvidenceStore, ref: str, observed_at: str) -> None:
    evidence.create({
        "ref": ref,
        "kind": "authority",
        "subject_ref": "repo:freshness",
        "observed_at": observed_at,
        "issuer": "host:test",
        "validator": "host-test-v1",
        "schema": "test-evidence-v1",
        "content_digest": ref,
    })


def test_after_state_entry_uses_latest_durable_revision_after_concurrent_reentry(
        tmp_path):
    identity = {
        "namespace_id": "tenant-a",
        "application_id": "assistant",
        "application_instance_id": "assistant-1",
        "workflow_id": "task-freshness",
        "subject_ref": "repo:freshness",
        "statework_id": "freshness-test",
        "contract_version": "1.0.0",
    }
    contract = {
        "initial_state": "S",
        "states": ["S", "T"],
        "transitions": [_edge("S", "T", "advance"),
                        _edge("T", "S", "return")],
    }
    registry = {"kinds": {"authority": {
        "authoritative": True,
        "allowed_issuers": ["host:test"],
        "validator": "host-test-v1",
        "schema": "test-evidence-v1",
    }}}
    state_store = SubjectStateStore(tmp_path / "subjects.json")
    evidence = EvidenceStore()
    controller_a = StandaloneStateWorkController(
        contract=contract, identity=identity, state_store=state_store,
        evidence_store=evidence, evidence_registry=registry)
    controller_b = StandaloneStateWorkController(
        contract=contract, identity=identity, state_store=state_store,
        evidence_store=evidence, evidence_registry=registry)

    first_s_entry = datetime.fromisoformat(
        controller_a.inspect()["updated_at"].replace("Z", "+00:00"))
    evidence_between_entries = max(first_s_entry, datetime.now(timezone.utc))
    stale_ref = "evidence-after-first-s"
    _evidence(evidence, stale_ref,
              evidence_between_entries.isoformat().replace("+00:00", "Z"))
    advanced = controller_b.request_transition(
        to_state="T", trigger="advance", evidence_refs=[stale_ref],
        expected_revision=controller_b.inspect()["revision"])
    assert advanced.allowed

    t_entry = datetime.fromisoformat(
        controller_b.inspect()["updated_at"].replace("Z", "+00:00"))
    assert first_s_entry <= evidence_between_entries < t_entry
    return_ref = "evidence-after-t"
    observed_after_t = max(t_entry, datetime.now(timezone.utc))
    _evidence(evidence, return_ref,
              observed_after_t.isoformat().replace("+00:00", "Z"))
    returned = controller_b.request_transition(
        to_state="S", trigger="return", evidence_refs=[return_ref],
        expected_revision=controller_b.inspect()["revision"])
    assert returned.allowed

    denied = controller_a.request_transition(
        to_state="T", trigger="advance", evidence_refs=[stale_ref],
        expected_revision=controller_a.inspect()["revision"])
    assert not denied.allowed
    assert denied.reason == "evidence predates current state entry"
