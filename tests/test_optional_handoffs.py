"""Optional handoff consumers: GodKiller -> TerraFormer/TestWorks, TerraFormer -> TestWorks.

The boundary/integration packets are optional data for their consumers:
fresh when the packet fingerprint exactly matches the observation context,
stale otherwise, and never force producer activation when absent.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.control_plane import PacketStore
from scripts.registry import open_compiled_registry
from scripts.workflow_planner import WorkflowPlanner

GODKILLER = "godkiller_boundary_packet"
TERRAFORMER = "terraformer_integration_packet"


def _compiled():
    return open_compiled_registry(ROOT)


def _planner(compiled):
    return WorkflowPlanner(
        compiled, ROOT,
        packet_store_factory=lambda packets: PacketStore(
            packets, packet_registry_data=compiled.get("packet_registry") or {},
            packet_schemas=compiled.get("packet_schemas") or {}))


def _fixtures(*wanted):
    packets = []
    for line in (ROOT / "fixtures" / "fixtures-valid.ndjson").read_text().splitlines():
        if not line.strip():
            continue
        packet = json.loads(line)
        if packet.get("packet_type") in wanted:
            packets.append(packet)
    return packets


def _identity_for(packet):
    return {"task_id": packet["task_id"], "subject_ref": packet["subject_ref"]}


def test_optional_consumer_wiring_resolves():
    compiled = _compiled()
    registry = (compiled.get("packet_registry") or {}).get("packets", {})
    assert set(registry[GODKILLER]["consumers"]) == {"terraformer", "testworks"}
    assert registry[TERRAFORMER]["consumers"] == ["testworks"]
    # freshness stays strict exact_context on the composition fingerprints
    assert registry[GODKILLER]["freshness"] == {
        "strategy": "exact_context",
        "packet_path": "payload.architecture_fingerprint",
        "context_path": "architecture_fingerprint",
    }
    assert registry[GODKILLER]["required_context"] == ["architecture_fingerprint"]
    assert registry[TERRAFORMER]["freshness"] == {
        "strategy": "exact_context",
        "packet_path": "payload.composition_fingerprint",
        "context_path": "composition_fingerprint",
    }
    assert registry[TERRAFORMER]["required_context"] == ["composition_fingerprint"]
    manifests = {row["id"]: row["manifest"] for row in compiled["stateworks"]}
    assert GODKILLER in manifests["terraformer"]["inputs"]["optional"]
    assert GODKILLER not in manifests["terraformer"]["inputs"]["required"]
    assert TERRAFORMER not in manifests["terraformer"]["inputs"]["required"]
    assert GODKILLER in manifests["testworks"]["inputs"]["optional"]
    assert TERRAFORMER in manifests["testworks"]["inputs"]["optional"]
    assert GODKILLER not in manifests["testworks"]["inputs"]["required"]
    assert TERRAFORMER not in manifests["testworks"]["inputs"]["required"]
    # optional wiring adds no activation coupling
    for statework_id in ("terraformer", "testworks"):
        composition = manifests[statework_id].get("composition") or {}
        assert composition.get("requires") == []
        assert composition.get("conflicts") == []


def test_fresh_optional_packet_resolves_and_stale_is_rejected():
    compiled = _compiled()
    packet = _fixtures(GODKILLER)[0]
    fingerprint = packet["payload"]["architecture_fingerprint"]
    identity = _identity_for(packet)

    planner = _planner(compiled)
    fresh = dict(identity, packet_records=(packet,),
                 observation_context={"architecture_fingerprint": fingerprint})
    store = PacketStore((packet,),
                        packet_registry_data=compiled.get("packet_registry") or {},
                        packet_schemas=compiled.get("packet_schemas") or {})
    assert store.get_current(
        GODKILLER, task_id=packet["task_id"], subject_ref=packet["subject_ref"],
        observation_context={"architecture_fingerprint": fingerprint}) is not None
    # stale fingerprint: the packet no longer counts as current
    assert store.get_current(
        GODKILLER, task_id=packet["task_id"], subject_ref=packet["subject_ref"],
        observation_context={"architecture_fingerprint": "sha256:rotated"}) is None

    stale = dict(identity, packet_records=(packet,),
                 observation_context={"architecture_fingerprint": "sha256:rotated"})
    assert planner._ordered_dependencies(
        [{"id": "terraformer"}], fresh, identity)[0]["id"] == "terraformer"
    assert planner._ordered_dependencies(
        [{"id": "terraformer"}], stale, identity)[0]["id"] == "terraformer"

    integration = _fixtures(TERRAFORMER)[0]
    composition = integration["payload"]["composition_fingerprint"]
    tstore = PacketStore((integration,),
                         packet_registry_data=compiled.get("packet_registry") or {},
                         packet_schemas=compiled.get("packet_schemas") or {})
    assert tstore.get_current(
        TERRAFORMER, task_id=integration["task_id"],
        subject_ref=integration["subject_ref"],
        observation_context={"composition_fingerprint": composition}) is not None
    assert tstore.get_current(
        TERRAFORMER, task_id=integration["task_id"],
        subject_ref=integration["subject_ref"],
        observation_context={"composition_fingerprint": "sha256:rotated"}) is None


def test_absent_optional_packet_leaves_eligibility_unchanged():
    compiled = _compiled()
    planner = _planner(compiled)
    identity = {"task_id": "optional-absent", "subject_ref": "repo:optional"}
    context = {"domains": (), "requested_statework_ids": ("terraformer",),
               "requested_flows": {"terraformer": "triage"},
               "packet_records": (), "observation_context": {},
               "allow_missing_required": False}
    eligibility = planner.eligible_routes(identity, context)
    assert [item["statework_id"] for item in eligibility["eligible_routes"]
            if item["route_type"] == "statework"] == ["terraformer"]
    resolution = planner.resolve_workflows(identity, context, ())
    assert [item["id"] for item in resolution["active_workflows"]] == ["terraformer"]
    assert [item["id"] for item in resolution["execution_order"]] == ["terraformer"]

    # a present-but-stale optional packet changes nothing either
    stale_godkiller = _fixtures(GODKILLER)[0]
    stale_context = dict(context, packet_records=(stale_godkiller,),
                         observation_context={"architecture_fingerprint": "sha256:rotated"})
    stale_resolution = planner.resolve_workflows(identity, stale_context, ())
    assert [item["id"] for item in stale_resolution["active_workflows"]] == ["terraformer"]


def test_terraformer_usable_without_godkiller_and_vice_versa():
    compiled = _compiled()
    planner = _planner(compiled)
    manifests = {row["id"]: row["manifest"] for row in compiled["stateworks"]}
    assert manifests["godkiller"]["inputs"]["required"] == ["task_context"]
    assert GODKILLER not in manifests["godkiller"]["inputs"]["required"]

    godkiller_only = {"task_id": "gk-alone", "subject_ref": "repo:alone"}
    godkiller_context = {"domains": (), "requested_statework_ids": ("godkiller",),
                         "requested_flows": {"godkiller": "triage"},
                         "packet_records": (), "observation_context": {},
                         "allow_missing_required": False}
    resolution = planner.resolve_workflows(godkiller_only, godkiller_context, ())
    assert [item["id"] for item in resolution["active_workflows"]] == ["godkiller"]
    # no producer activation is forced: neither root pulls the other in
    assert "terraformer" not in [item["id"] for item in resolution["execution_order"]]

    terraformer_only = {"task_id": "tf-alone", "subject_ref": "repo:alone"}
    terraformer_context = {"domains": (), "requested_statework_ids": ("terraformer",),
                           "requested_flows": {"terraformer": "triage"},
                           "packet_records": (), "observation_context": {},
                           "allow_missing_required": False}
    resolution = planner.resolve_workflows(terraformer_only, terraformer_context, ())
    assert [item["id"] for item in resolution["execution_order"]] == ["terraformer"]


def test_testworks_evaluates_without_either_optional_packet():
    compiled = _compiled()
    planner = _planner(compiled)
    identity = {"task_id": "tw-alone", "subject_ref": "repo:alone"}
    context = {"domains": (), "requested_statework_ids": ("testworks",),
               "requested_flows": {"testworks": "select"},
               "packet_records": (), "observation_context": {},
               "allow_missing_required": False}
    eligibility = planner.eligible_routes(identity, context)
    assert [item["statework_id"] for item in eligibility["eligible_routes"]
            if item["route_type"] == "statework"] == ["testworks"]
    resolution = planner.resolve_workflows(identity, context, ())
    assert [item["id"] for item in resolution["active_workflows"]] == ["testworks"]
    assert [item["id"] for item in resolution["execution_order"]] == ["testworks"]
