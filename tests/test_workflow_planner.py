from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.control_plane import PacketStore
from scripts.registry import open_compiled_registry
from scripts.workflow_planner import WorkflowPlanner


ROOT = Path(__file__).resolve().parents[1]


def _planner() -> WorkflowPlanner:
    compiled = open_compiled_registry(ROOT)
    return WorkflowPlanner(
        compiled, ROOT,
        packet_store_factory=lambda packets: PacketStore(
            packets, packet_registry_data=compiled.get("packet_registry") or {},
            packet_schemas=compiled.get("packet_schemas") or {}))


def _context() -> dict:
    return {
        "domains": ("terminal UI layout",),
        "phase": "domain_state",
        "operation": "implement",
        "trigger": "mutation",
        "task_shape": "implement",
        "current_state": "DESIGNED",
        "observation_context": {},
        "statework_subject_refs": {},
        "packet_records": (),
        "allow_missing_required": False,
    }


def test_csw_planner_owns_eligibility_composition_and_flow_pins():
    planner = _planner()
    identity = {"task_id": "planner-test", "subject_ref": "repo:fixture"}
    context = _context()

    eligibility = planner.eligible_routes(identity, context)
    routes = list(eligibility["eligible_routes"])
    assert any(row["route_type"] == "statework" and row["route"] == "tuid"
               for row in routes)
    assert any(row["route_type"] == "flow" and row["route"] == "implement"
               for row in routes)
    assert not any(row["route_type"] == "flow" and row["route"] == "test"
                   for row in routes)

    resolution = planner.resolve_workflows(identity, context, ())
    assert resolution["dependency_checks_passed"] is True
    assert [row["id"] for row in resolution["active_workflows"]] == ["tuid"]
    active = resolution["active_workflows"][0]
    assert active["subject_ref"] == "repo:fixture"
    assert active["selected_flow"][0] == "tuid/flows/implement/flow.md"
    assert "statework:tuid" in resolution["capsules"]
    assert resolution["registry_version"] == "2.0.0"


def test_csw_planner_rejects_a_preference_that_is_not_eligible():
    planner = _planner()
    try:
        planner.resolve_workflows(
            {"task_id": "planner-test", "subject_ref": "repo:fixture"},
            _context(),
            ({"route_type": "flow", "statework_id": "tuid",
              "route": "missing-flow", "disposition": "prefer"},))
    except ValueError as exc:
        assert "ineligible" in str(exc)
    else:
        raise AssertionError("CSW accepted a preference outside its legal flow set")
