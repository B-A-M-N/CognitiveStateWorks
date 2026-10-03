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
    assert active["exclusive_group"] == "tui_state"
    assert active["composition"]["mode"] == "exclusive"
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


def test_csw_planner_accepts_explicit_roots_for_legacy_host_adapters():
    planner = _planner()
    identity = {"task_id": "planner-test", "subject_ref": "repo:fixture"}
    context = {**_context(), "domains": (), "requested_statework_ids": ("tuid",)}

    eligibility = planner.eligible_routes(identity, context)
    resolution = planner.resolve_workflows(identity, context, ())

    assert [item["statework_id"] for item in eligibility["eligible_routes"]
            if item["route_type"] == "statework"] == ["tuid"]
    assert [item["id"] for item in resolution["execution_order"]] == ["tuid"]


def test_csw_planner_owns_dependency_cycle_and_unknown_packet_failures(tmp_path):
    class EmptyPacketStore:
        @staticmethod
        def get_current(*_args, **_kwargs):
            return None

    def planner_for(manifests, packet_registry):
        compiled = {"stateworks": [
            {"id": statework_id, "manifest": manifest,
             "bundle_root": str(tmp_path / statework_id)}
            for statework_id, manifest in manifests.items()],
            "packet_registry": packet_registry,
        }
        return WorkflowPlanner(
            compiled, tmp_path,
            packet_store_factory=lambda _packets: EmptyPacketStore())

    cycle = planner_for({
        "a": {"id": "a", "composition": {"requires": ["b"]}},
        "b": {"id": "b", "composition": {"requires": ["a"]}},
    }, {"packets": {}})
    try:
        cycle.resolve_workflows(
            {"task_id": "cycle", "subject_ref": "repo:cycle"},
            {"domains": (), "requested_statework_ids": ("a",)}, ())
    except ValueError as exc:
        assert "cycle" in str(exc).lower()
    else:
        raise AssertionError("CSW accepted a dependency cycle")

    unknown = planner_for({
        "consumer": {"id": "consumer", "inputs": {
            "required": ["missing_packet"], "optional": []}},
    }, {"packets": {}})
    try:
        unknown.resolve_workflows(
            {"task_id": "unknown", "subject_ref": "repo:unknown"},
            {"domains": (), "requested_statework_ids": ("consumer",),
             "allow_missing_required": False}, ())
    except ValueError as exc:
        assert "missing_packet" in str(exc)
    else:
        raise AssertionError("CSW accepted an unregistered required packet")


def test_csw_planner_returns_candidates_for_ambiguous_domain_matches(tmp_path):
    manifests = {
        statework_id: {"id": statework_id, "triggers": ["widget state"]}
        for statework_id in ("alpha", "beta")
    }
    compiled = {"stateworks": [
        {"id": statework_id, "manifest": manifest,
         "bundle_root": str(tmp_path / statework_id)}
        for statework_id, manifest in manifests.items()],
        "packet_registry": {"packets": {}},
    }
    planner = WorkflowPlanner(
        compiled, tmp_path,
        packet_store_factory=lambda _packets: object())

    try:
        planner.eligible_routes(
            {"task_id": "ambiguous", "subject_ref": "repo:ambiguous"},
            {"domains": ("widget state",), "allow_missing_required": True})
    except ValueError as exc:
        assert getattr(exc, "candidates", ()) == ("alpha", "beta")
    else:
        raise AssertionError("CSW silently chose one of two tied roots")


def test_planner_and_authority_share_the_same_canonical_composition_rules():
    from scripts import workflow_authority
    from scripts import composition_rules

    assert workflow_authority.validate_selection is composition_rules.validate_selection


def test_composition_rules_check_bidirectional_conflicts_and_requirements():
    from scripts.composition_rules import validate_selection

    manifests = {
        "base": {"composition": {"requires": [], "conflicts": ["addon"]}},
        "addon": {"composition": {"requires": [], "conflicts": []}},
        "consumer": {"composition": {"requires": ["base"], "conflicts": []}},
    }
    try:
        validate_selection(manifests, {"base", "addon"})
    except ValueError as exc:
        assert "conflicts" in str(exc)
    else:
        raise AssertionError("one-sided conflicts were not enforced")

    try:
        validate_selection(manifests, {"consumer"})
    except ValueError as exc:
        assert "requirements" in str(exc)
    else:
        raise AssertionError("missing requirements were not enforced")


def test_exclusive_group_allows_only_dependency_members_to_compose():
    from scripts.composition_rules import validate_selection

    manifests = {
        "base": {"exclusive_group": "g", "composition": {
            "group": "g", "mode": "exclusive", "requires": [], "conflicts": []}},
        "consumer": {"composition": {
            "group": "g", "mode": "composable", "requires": ["base"],
            "conflicts": []}},
        "peer": {"composition": {
            "group": "g", "mode": "composable", "requires": [], "conflicts": []}},
    }
    validate_selection(manifests, {"base", "consumer"})
    try:
        validate_selection(manifests, {"base", "peer"})
    except ValueError as exc:
        assert "exclusive StateWork group" in str(exc)
    else:
        raise AssertionError("independent members of an exclusive group composed")
