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


def load_yaml(path: Path) -> Any:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_transition_contract(name: str, bundle_roots: Dict[str, Path],
                             manifests: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    engine = manifests[name].get("engine") or {}
    path = bundle_roots[name] / str(engine.get("contract") or "transitions.yaml")
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


def main(root: Path = ROOT) -> int:
    root = Path(root).resolve()
    problems: List[str] = []
    infos: List[str] = []

    registry_path = root / "registry.yaml"
    if not registry_path.exists():
        print("Missing registry.yaml")
        return 1
    registry = load_yaml(registry_path)
    try:
        from scripts.registry import load_compiled_registry
        compiled = load_compiled_registry(root)
        compiled_entries = {
            str(entry["id"]): entry for entry in compiled.get("stateworks") or ()}
    except Exception as exc:
        problems.append(f"compiled registry invalid: {exc}")
        compiled = {}
        compiled_entries = {}
    names = list(compiled_entries) or registry.get("stateworks", [])
    if not names or len(names) != len(set(names)):
        problems.append("compiled StateWork registry missing or duplicated")
    bundle_roots = {
        name: Path(str(compiled_entries[name]["bundle_root"]))
        if name in compiled_entries else root / name
        for name in names
    }

    # manifest schema
    schema_path = root / "schemas" / "statework-manifest.schema.json"
    if not schema_path.exists():
        problems.append("Missing schemas/statework-manifest.schema.json")
        schema = None
    else:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

    import jsonschema
    manifests: Dict[str, Dict[str, Any]] = {}
    for name in names:
        owner = bundle_roots.get(name, root / name)
        manifest_path = owner / "manifest.yaml"
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
        if entry and not (owner / entry).exists() and not (root / entry).exists():
            problems.append(f"{name}: entrypoint {entry!r} does not exist")
        # Advisory entrypoints are explicit bundle-local paths. CSW keeps
        # integration capability names opaque to the host integration.
        advisory_entrypoint = data.get("advisory_entrypoint")
        if advisory_entrypoint:
            path = Path(str(advisory_entrypoint))
            if (path.is_absolute() or ".." in path.parts
                    or not (owner / path).is_file()
                    or (owner / path).is_symlink()):
                problems.append(f"{name}: invalid advisory_entrypoint {advisory_entrypoint!r}")
        manifests[name] = data

    flow_schema_path = root / "schemas" / "statework-flow.schema.json"
    transition_schema_path = root / "schemas" / "transition-contract.schema.json"
    milestone_schema_path = root / "schemas" / "milestone-contract.schema.json"
    packet_registry_schema_path = root / "schemas" / "packet-registry.schema.json"
    flow_schema = json.loads(flow_schema_path.read_text(encoding="utf-8"))
    transition_schema = json.loads(transition_schema_path.read_text(encoding="utf-8"))
    milestone_schema = json.loads(milestone_schema_path.read_text(encoding="utf-8"))
    packet_registry_schema = json.loads(packet_registry_schema_path.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=load_yaml(root / "schemas" / "packet-registry.yaml"),
                            schema=packet_registry_schema)
    except Exception as exc:
        problems.append(f"packet-registry.yaml schema violation: {getattr(exc, 'message', exc)}")

    # flow/runtime specialist budget: each flow declares required/optional
    # specialists; required + loaded optional must respect the context budget
    for name, data in manifests.items():
        budget = data.get("context_budget", "medium")
        limit = {"low": 1, "medium": 2, "high": 3}.get(budget, 2)
        owner = bundle_roots.get(name, root / name)
        flows_dir = owner / "flows"
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
                    if str((data.get("engine") or {}).get("kind") or "") != "state_machine":
                        problems.append(
                            f"{name}: non-state-machine flow {flow_md.parent.name} declares states")
                        contract_states = set()
                    else:
                        contract_states = set(
                            (load_transition_contract(name, bundle_roots, manifests) or {}).get(
                                "states") or [])
                    referenced = set(flow_states.get("through") or [])
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
    from scripts.workflow_engines import MilestoneWorkflowEngine
    evidence_registry = compiled.get("evidence_registry") or {"kinds": {}}
    for name in names:
        entry = compiled_entries.get(name) or {}
        manifest = manifests.get(name) or {}
        owner = bundle_roots.get(name, root / name)
        engine = manifest.get("engine") or {}
        contract_path = owner / str(engine.get("contract") or "transitions.yaml")
        if not contract_path.is_file():
            problems.append(f"{name}: missing workflow contract {contract_path.name}")
            continue
        try:
            contract = load_yaml(contract_path) or {}
        except Exception as exc:
            problems.append(f"{name}: workflow contract is invalid YAML: {exc}")
            continue
        engine_kind = str(engine.get("kind") or "state_machine")
        if engine_kind == "milestone":
            try:
                jsonschema.validate(instance=contract, schema=milestone_schema)
                MilestoneWorkflowEngine().validate_contract(contract)
            except Exception as exc:
                problems.append(f"{name}: invalid milestone contract: {exc}")
            continue
        if engine_kind != "state_machine":
            # Registry compilation has already verified an explicitly trusted
            # custom engine and its contract. This validator does not import
            # arbitrary extension code a second time.
            if not entry:
                problems.append(f"{name}: custom workflow engine is not compiled")
            continue
        try:
            jsonschema.validate(instance=contract, schema=transition_schema)
            # Consequential edges must use evidence kinds registered by the host.
            # Ordinary observation edges may still use StateWork-specific kinds.
            TransitionEngine(contract, evidence_registry=evidence_registry, require_registered=True)
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
    packet_schemas = dict(compiled.get("packet_schemas") or {})
    packet_reg_path = root / "schemas" / "packet-registry.yaml"
    if not packet_reg_path.exists():
        problems.append("Missing schemas/packet-registry.yaml")
        packets = {}
    else:
        packets = (compiled.get("packet_registry") or {}).get(
            "packets", load_yaml(packet_reg_path).get("packets", {}))
    from scripts.contracts import validate_packet
    reference_schemas = [json.loads(path.read_text(encoding="utf-8"))
                         for path in sorted((root / "schemas").glob("*.json"))]

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
            if packet not in packet_schemas:
                problems.append(f"{name}: packet {packet} has no compiled schema")
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
    fixtures_dir = root / "fixtures"
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
                schema = packet_schemas.get(str(packet.get("packet_type")))
                if not isinstance(schema, dict):
                    problems.append(
                        f"{fixture.name}:{lineno}: packet schema is not compiled")
                    continue
                try:
                    validate_packet(packet, schema, reference_schemas=reference_schemas)
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
            schema = packet_schemas.get(str(packet.get("packet_type")))
            if not isinstance(schema, dict):
                problems.append(f"{neg_path.name}:{lineno}: packet schema is not compiled")
                continue
            try:
                validate_packet(packet, schema, reference_schemas=reference_schemas)
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


validate_stateworks = main


if __name__ == "__main__":
    sys.exit(main())
