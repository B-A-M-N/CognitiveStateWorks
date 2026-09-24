#!/usr/bin/env python3
"""Validate CognitiveStateWork: registry, manifest schema, entrypoints,
packet registry, producer/consumer validity, handoff fixtures, and semantic
consistency. FrameWorks' validate-framework.py runs this as a secondary
integration check; StateWork owns this validator so FrameWorks does not
become the validation God Object for sibling trees.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FRAMEWORK_STAGES = {"owl", "anchor", "dox", "fuse", "flow", "ward", "sispis"}


def load_yaml(path: Path) -> Any:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_transition_contract(name: str) -> Dict[str, Any]:
    path = ROOT / name / "transitions.yaml"
    if not path.exists():
        return {}
    import yaml as yaml_module
    return yaml_module.safe_load(path.read_text(encoding="utf-8")) or {}


def manifest_inputs(data: Dict[str, Any]) -> tuple[List[str], List[str]]:
    """Single canonical parser for StateWork packet inputs."""
    inputs = data.get("inputs")
    if isinstance(inputs, dict):
        required = [p for p in inputs.get("required", []) if p != "task_context"]
        optional = [p for p in inputs.get("optional", []) if p != "task_context"]
    else:
        required = [p for p in data.get("consumes", []) if p != "task_context"]
        optional = []
    return required, optional


def _hard_check_timestamp(packet: Dict[str, Any]) -> None:
    """Hard date-time enforcement: the installed jsonschema FormatChecker
    does not register draft 2020-12 date-time, so a non-datetime observed_at
    must not silently pass."""
    from datetime import datetime
    try:
        datetime.fromisoformat(packet["observed_at"].replace("Z", "+00:00"))
    except Exception as exc:
        raise jsonschema.ValidationError(f"observed_at is not a valid date-time: {exc}")


def main() -> int:
    problems: List[str] = []
    infos: List[str] = []

    registry_path = ROOT / "registry.yaml"
    if not registry_path.exists():
        print("Missing registry.yaml")
        return 1
    registry = load_yaml(registry_path)
    names = registry.get("stateworks", [])
    if not names or len(names) != len(set(names)):
        problems.append("registry stateworks missing or duplicated")

    # manifest schema
    schema_path = ROOT / "schemas" / "statework-manifest.schema.json"
    if not schema_path.exists():
        problems.append("Missing schemas/statework-manifest.schema.json")
        schema = None
    else:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

    import jsonschema
    manifests: Dict[str, Dict[str, Any]] = {}
    for name in names:
        manifest_path = ROOT / name / "manifest.yaml"
        if not manifest_path.exists():
            problems.append(f"{name}: missing manifest.yaml")
            continue
        try:
            data = load_yaml(manifest_path)
        except Exception as exc:
            problems.append(f"{name}/manifest.yaml invalid YAML: {exc}")
            continue
        if data.get("id") != name:
            problems.append(f"{name}/manifest.yaml id mismatch: {data.get('id')!r}")
        if schema is not None:
            try:
                jsonschema.validate(instance=data, schema=schema)
            except jsonschema.ValidationError as exc:
                problems.append(f"{name}/manifest.yaml schema violation: {exc.message}")
        # entrypoint exists
        entry = data.get("entrypoint")
        if entry and not (ROOT / entry).exists():
            problems.append(f"{name}: entrypoint {entry!r} does not exist")
        # core requirements recognized
        bad_reqs = [r for r in data.get("core_requirements", []) if r not in FRAMEWORK_STAGES]
        if bad_reqs:
            problems.append(f"{name}: unknown core_requirements {bad_reqs}")
        manifests[name] = data

    flow_schema_path = ROOT / "schemas" / "statework-flow.schema.json"
    transition_schema_path = ROOT / "schemas" / "transition-contract.schema.json"
    packet_registry_schema_path = ROOT / "schemas" / "packet-registry.schema.json"
    flow_schema = json.loads(flow_schema_path.read_text(encoding="utf-8"))
    transition_schema = json.loads(transition_schema_path.read_text(encoding="utf-8"))
    packet_registry_schema = json.loads(packet_registry_schema_path.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=load_yaml(ROOT / "schemas" / "packet-registry.yaml"),
                            schema=packet_registry_schema)
    except Exception as exc:
        problems.append(f"packet-registry.yaml schema violation: {getattr(exc, 'message', exc)}")

    # flow/runtime specialist budget: each flow declares required/optional
    # specialists; required + loaded optional must respect the context budget
    for name, data in manifests.items():
        budget = data.get("context_budget", "medium")
        limit = {"low": 1, "medium": 2, "high": 3}.get(budget, 2)
        flows_dir = ROOT / name / "flows"
        if not flows_dir.is_dir():
            continue
        for flow_md in flows_dir.glob("*/flow.md"):
            try:
                ftext = flow_md.read_text(encoding="utf-8")
                if not ftext.startswith("---"):
                    problems.append(f"{name}: flow {flow_md.parent.name} missing frontmatter")
                    continue
                fm = ftext.split("---", 2)[1]
                import yaml as _yaml
                fdata = _yaml.safe_load(fm) or {}
                try:
                    jsonschema.validate(instance=fdata, schema=flow_schema)
                except jsonschema.ValidationError as exc:
                    problems.append(f"{name}: flow {flow_md.parent.name} schema violation: {exc.message}")
                if fdata.get("flow") != flow_md.parent.name:
                    problems.append(f"{name}: flow metadata name {fdata.get('flow')!r} does not match directory {flow_md.parent.name!r}")
                flow_states = fdata.get("states") or {}
                if flow_states:
                    contract_states = set(
                        (load_transition_contract(name) or {}).get("states") or [])
                    referenced = set(flow_states.get("from") or []) | set(
                        flow_states.get("through") or [])
                    if not referenced.issubset(contract_states):
                        problems.append(
                            f"{name}: flow {flow_md.parent.name} references undeclared states "
                            f"{sorted(referenced - contract_states)}")
                if "required_specialists" not in fdata or "optional_specialists" not in fdata:
                    problems.append(f"{name}: flow {flow_md.parent.name} must explicitly declare specialist lists")
            except Exception as exc:
                problems.append(f"{name}: flow {flow_md.name} frontmatter invalid: {exc}")
                continue
            req = fdata.get("required_specialists", []) or []
            opt = fdata.get("optional_specialists", []) or []
            req_paths = []
            for rel in req + opt:
                candidate = (flow_md.parent / rel).resolve()
                if not candidate.exists():
                    problems.append(f"{name}: flow {flow_md.parent.name} specialist {rel!r} does not exist")
                elif rel in req:
                    req_paths.append(candidate)
            if (len(req) + len(opt)) > limit:
                problems.append(
                    f"{name}: flow {flow_md.parent.name} exceeds specialist limit "
                    f"({len(req)} required + {len(opt)} optional > {limit} for "
                    f"context_budget={budget})")
            if not isinstance(fdata.get("required_specialists", []), list):
                problems.append(f"{name}: flow {flow_md.parent.name} required_specialists not a list")
            if not isinstance(fdata.get("optional_specialists", []), list):
                problems.append(f"{name}: flow {flow_md.parent.name} optional_specialists not a list")

    # machine-readable transition contracts
    from scripts.control_plane import TransitionEngine
    from scripts.control_plane import load_evidence_kind_registry
    try:
        evidence_registry = load_evidence_kind_registry()
    except Exception as exc:
        problems.append(f"evidence-kind registry invalid: {exc}")
        evidence_registry = {"kinds": {}}
    for name in names:
        contract = load_transition_contract(name)
        if not contract:
            problems.append(f"{name}: missing transitions.yaml machine contract")
            continue
        try:
            jsonschema.validate(instance=contract, schema=transition_schema)
            # Ordinary StateWork observations remain extensible; semantic
            # authority names are still registry-validated by TransitionEngine.
            TransitionEngine(contract, evidence_registry=evidence_registry, require_registered=False)
        except Exception as exc:
            problems.append(f"{name}: invalid transition contract: {exc}")
            continue
        states = set(contract.get("states") or [])
        edges = contract.get("transitions") or []
        for edge in edges:
            origin = edge.get("from")
            destination = edge.get("to")
            if origin != "*" and origin not in states:
                problems.append(f"{name}: transition origin {origin!r} is not declared")
            if destination not in states:
                problems.append(f"{name}: transition destination {destination!r} is not declared")
            if not edge.get("trigger"):
                problems.append(f"{name}: transition {origin!r} -> {destination!r} has no trigger")
            required = edge.get("required_evidence") or []
            if not required or any(not isinstance(item, str) or not item for item in required):
                problems.append(f"{name}: transition {origin!r} -> {destination!r} has invalid evidence kinds")
        identity = set()
        for edge in edges:
            item = (edge.get("from"), edge.get("to"), edge.get("trigger"))
            if item in identity:
                problems.append(f"{name}: duplicate transition {item}")
            identity.add(item)
        reachable = set()
        initial = contract.get("initial_state") or states
        if isinstance(initial, str):
            initial = {initial}
        if not set(initial).issubset(states):
            problems.append(f"{name}: initial_state is not a declared state")
            initial = set()
        pending = list(initial)
        while pending:
            current = pending.pop()
            if current in reachable:
                continue
            reachable.add(current)
            for edge in edges:
                if edge.get("from") == current or edge.get("from") == "*":
                    pending.append(edge.get("to"))
        unreachable_completions = set(contract.get("completion_states") or []) - reachable
        if unreachable_completions:
            problems.append(f"{name}: completion states unreachable: {sorted(unreachable_completions)}")
        external_entries = set(contract.get("external_entry_states") or [])
        unreachable = states - reachable - external_entries
        if unreachable:
            problems.append(f"{name}: states unreachable from initial_state: {sorted(unreachable)}")
        normal_path = list(contract.get("normal_path") or [])
        if not normal_path or normal_path[0] != contract.get("initial_state"):
            problems.append(f"{name}: normal_path must start at initial_state")
        if normal_path and normal_path[-1] not in set(contract.get("completion_states") or []):
            problems.append(f"{name}: normal_path must terminate in a completion state")
        if any(state not in states for state in normal_path):
            problems.append(f"{name}: normal_path references undeclared state")
        edge_index = {(edge.get("from"), edge.get("to")): edge for edge in edges}
        for origin, destination in zip(normal_path, normal_path[1:]):
            edge = edge_index.get((origin, destination))
            if edge is None or edge.get("from") == "*":
                problems.append(f"{name}: normal_path lacks explicit edge {origin!r} -> {destination!r}")
            elif edge.get("path_class", "normal") != "normal":
                problems.append(f"{name}: normal_path uses non-normal edge {origin!r} -> {destination!r}")
        outgoing = {state: [] for state in states}
        for edge in edges:
            if edge.get("from") != "*":
                outgoing.setdefault(edge.get("from"), []).append(edge)
        completion_states = set(contract.get("completion_states") or [])
        for state, state_edges in outgoing.items():
            if not state_edges and state not in completion_states:
                problems.append(f"{name}: nonterminal state {state!r} has no exit")
        if any(edge.get("from") == "*" and edge.get("path_class", "external") == "normal"
               for edge in edges):
            problems.append(f"{name}: wildcard transition cannot be part of normal path")

    # packet registry
    packet_reg_path = ROOT / "schemas" / "packet-registry.yaml"
    if not packet_reg_path.exists():
        problems.append("Missing schemas/packet-registry.yaml")
        packets = {}
    else:
        packets = load_yaml(packet_reg_path).get("packets", {})

    for name, data in manifests.items():
        for packet in data.get("emits", []):
            if packet == "standard_assessment":
                continue
            meta = packets.get(packet)
            if meta is None:
                problems.append(f"{name}: emits unregistered packet {packet!r}")
                continue
            if meta.get("producer") != name:
                problems.append(f"{name}: packet {packet} registry producer is {meta.get('producer')!r}")
            schema_name = meta.get("schema")
            if schema_name and not (ROOT / "schemas" / schema_name).exists():
                problems.append(f"{name}: packet {packet} schema {schema_name!r} missing")
        if "consumes" in data:
            problems.append(f"{name}: manifest uses obsolete consumes; migrate to inputs.required/inputs.optional")
        if not isinstance(data.get("inputs"), dict) or not {"required", "optional"}.issubset(data["inputs"]):
            problems.append(f"{name}: manifest must declare inputs.required and inputs.optional")
            continue
        required_inputs, optional_inputs = manifest_inputs(data)
        for packet in required_inputs + optional_inputs:
            meta = packets.get(packet)
            if meta is None:
                problems.append(f"{name}: consumes unregistered packet {packet!r}")
                continue
            producer = meta.get("producer")
            producer_manifest = manifests.get(producer)
            if producer_manifest is None:
                problems.append(f"{name}: packet {packet} producer {producer!r} has no manifest")
            elif packet not in producer_manifest.get("emits", []):
                problems.append(f"{name}: packet {packet} producer {producer!r} does not emit it")
            if name not in (meta.get("consumers") or []):
                problems.append(f"{name}: packet {packet} registry consumers omit {name}")

    # every registered packet has a schema and a producer
    for packet, meta in packets.items():
        producer_manifest = manifests.get(meta.get("producer"))
        if producer_manifest is not None:
            for consumer in meta.get("consumers") or []:
                consumer_manifest = manifests.get(consumer)
                if consumer_manifest is None:
                    problems.append(f"packet {packet}: consumer {consumer!r} has no manifest")
                    continue
                req_c, opt_c = manifest_inputs(consumer_manifest)
                if packet not in req_c + opt_c:
                    problems.append(f"packet {packet}: consumer {consumer!r} does not declare it")
        if not meta.get("schema"):
            problems.append(f"packet {packet}: no schema registered")
        if not meta.get("producer"):
            problems.append(f"packet {packet}: no producer registered")
        producer_manifest = manifests.get(meta.get("producer"))
        if producer_manifest is not None and producer_manifest.get("handoff") not in (producer_manifest.get("emits") or []):
            problems.append(f"{meta.get('producer')}: manifest.handoff is not declared in emits")

    # handoff fixture validation: fixtures/fixtures-valid.ndjson must contain
    # at least one valid fixture per registered packet type; the validator
    # FAILS when a registered packet has no fixture (the schema path would
    # otherwise validate zero examples).
    fixtures_dir = ROOT / "fixtures"
    fixture_types: Dict[str, bool] = {}
    if fixtures_dir.is_dir():
        for fixture in sorted(fixtures_dir.glob("fixtures-valid.ndjson")):
            for lineno, line in enumerate(fixture.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    packet = json.loads(line)
                except json.JSONDecodeError as exc:
                    problems.append(f"{fixture.name}:{lineno}: invalid JSON: {exc}")
                    continue
                meta = packets.get(packet.get("packet_type"))
                if meta is None:
                    problems.append(f"{fixture.name}:{lineno}: unregistered packet type {packet.get('packet_type')!r}")
                    continue
                schema_path_abs = ROOT / "schemas" / meta["schema"]
                if not schema_path_abs.exists():
                    problems.append(f"{fixture.name}:{lineno}: schema {meta['schema']} missing")
                    continue
                try:
                    # local referencing.Registry binds every schema's absolute
                    # $id to the local file — never network resolution.
                    from referencing import Registry, Resource
                    from jsonschema import Draft202012Validator
                    registry = Registry()
                    for reg_schema_path in sorted((ROOT / "schemas").glob("*.json")):
                        reg_schema = json.loads(reg_schema_path.read_text(encoding="utf-8"))
                        uri = reg_schema.get("$id")
                        if uri:
                            registry = registry.with_resource(uri, Resource.from_contents(reg_schema))
                    schema = json.loads(schema_path_abs.read_text(encoding="utf-8"))
                    Draft202012Validator(schema, registry=registry, format_checker=jsonschema.FormatChecker()).validate(packet)
                    _hard_check_timestamp(packet)
                except jsonschema.ValidationError as exc:
                    problems.append(f"{fixture.name}:{lineno}: {exc.message}")
                    continue
                fixture_types[packet["packet_type"]] = True
    # every registered packet needs at least one valid fixture
    for packet_name, meta in packets.items():
        if not fixture_types.get(packet_name):
            problems.append(f"packet {packet_name}: no valid fixture in fixtures/fixtures-valid.ndjson ")

    # negative fixtures: must fail schema validation (wrong producer, wrong
    # packet type, missing envelope field, invalid timestamp, malformed payload)
    negative_checks = [
        ("wrong-producer.ndjson", "expected constraint violation"),
        ("wrong-packet-type.ndjson", "expected constraint violation"),
        ("missing-envelope-field.ndjson", "required property"),
        ("invalid-timestamp.ndjson", "not a.*date-time|timestamp"),
        ("malformed-payload.ndjson", "required property|additionalProperties"),
    ]
    for fname, expected in negative_checks:
        neg_path = fixtures_dir / fname
        if not neg_path.exists():
            problems.append(f"Negative fixture missing: fixtures/{fname}")
            continue
        for lineno, line in enumerate(neg_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                packet = json.loads(line)
            except json.JSONDecodeError as exc:
                problems.append(f"{neg_path.name}:{lineno}: invalid JSON: {exc}")
                continue
            meta = packets.get(packet.get("packet_type"))
            if meta is None:
                problems.append(f"{neg_path.name}:{lineno}: unregistered packet type {packet.get('packet_type')!r}")
                continue
            schema_path_abs = ROOT / "schemas" / meta["schema"]
            try:
                from referencing import Registry, Resource
                from jsonschema import Draft202012Validator
                registry = Registry()
                for reg_schema_path in sorted((ROOT / "schemas").glob("*.json")):
                    reg_schema = json.loads(reg_schema_path.read_text(encoding="utf-8"))
                    uri = reg_schema.get("$id")
                    if uri:
                        registry = registry.with_resource(uri, Resource.from_contents(reg_schema))
                schema = json.loads(schema_path_abs.read_text(encoding="utf-8"))
                Draft202012Validator(schema, registry=registry, format_checker=jsonschema.FormatChecker()).validate(packet)
                _hard_check_timestamp(packet)
                problems.append(f"{neg_path.name}:{lineno}: expected negative fixture to FAIL, but it validated")
            except jsonschema.ValidationError:
                pass  # expected failure
            except jsonschema.SchemaError:
                problems.append(f"{neg_path.name}:{lineno}: schema error while validating negative fixture")

    if problems:
        print("StateWork validation failed:")
        for msg in problems:
            print(f"- {msg}")
        return 1
    print(f"StateWork validation passed ({len(manifests)} manifests, {len(packets)} packet types)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
