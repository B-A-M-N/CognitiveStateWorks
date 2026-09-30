from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[1]


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---"), path
    parts = text.split("---", 2)
    assert len(parts) == 3, path
    return yaml.safe_load(parts[1]) or {}


def _flows(statework_id: str) -> dict[str, dict]:
    return {path.parent.name: _frontmatter(path)
            for path in sorted((ROOT / statework_id / "flows").glob("*/flow.md"))}


def test_all_installed_flows_have_selectors_or_one_explicit_fallback():
    registry = yaml.safe_load((ROOT / "registry.yaml").read_text(encoding="utf-8"))
    flow_schema = json.loads((ROOT / "schemas/statework-flow.schema.json").read_text())
    manifest_schema = json.loads((ROOT / "schemas/statework-manifest.schema.json").read_text())

    for statework_id in registry["stateworks"]:
        manifest = yaml.safe_load((ROOT / statework_id / "manifest.yaml").read_text())
        jsonschema.validate(manifest, manifest_schema)
        flows = _flows(statework_id)
        if not flows:
            continue
        fallbacks = []
        for name, flow in flows.items():
            jsonschema.validate(flow, flow_schema)
            assert flow["flow"] == name
            if flow.get("fallback") is True:
                fallbacks.append(name)
            has_selector = any(flow.get(key) for key in
                               ("operations", "triggers", "task_shapes", "domain_tags"))
            has_selector = has_selector or bool((flow.get("states") or {}).get("from"))
            assert has_selector or flow.get("fallback") is True, (statework_id, name)
        assert len(fallbacks) == 1, (statework_id, fallbacks)


def test_tuid_discriminator_excludes_generic_layout_and_includes_terminal_layout():
    manifest = yaml.safe_load((ROOT / "tuid/manifest.yaml").read_text())
    match = manifest["match"]

    def matches(text: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        return any(re.sub(r"[^a-z0-9]+", " ", term.lower()).strip() in normalized
                   for term in match["required_any"])

    assert not matches("layout")
    assert matches("terminal UI layout")
    assert all(term in manifest["triggers"] for term in ("terminal interface", "TUI"))


def test_tuid_implementation_and_test_flows_are_separately_eligible():
    flows = _flows("tuid")
    implementation = flows["implement"]
    testing = flows["test"]
    assert "test" not in implementation.get("operations", [])
    assert testing["operations"] == ["test", "verify", "validate"]
    assert testing["triggers"] == ["validation_requested", "test_requested"]


def test_every_statework_runtime_vocabulary_matches_transition_contracts():
    registry = yaml.safe_load((ROOT / "registry.yaml").read_text())
    pair_re = re.compile(
        r"\b([A-Z][A-Z0-9_]*(?:\s*/\s*[A-Z][A-Z0-9_]*)*)\s*→\s*"
        r"([A-Z][A-Z0-9_]*(?:\s*/\s*[A-Z][A-Z0-9_]*)*)\b")
    heading_re = re.compile(
        r"(?im)^#{1,6}\s+State vocabulary\s*$([\s\S]*?)(?=^#{1,6}\s+|\Z)")

    for statework_id in registry["stateworks"]:
        owner = ROOT / statework_id
        capsule = (owner / "runtime.md").read_text(encoding="utf-8")
        contract = yaml.safe_load((owner / "transitions.yaml").read_text())
        match = heading_re.search(capsule)
        if not match:
            continue
        declared_states = set(contract.get("states", []))
        edges = contract.get("transitions", [])
        for origin_text, destination_text in pair_re.findall(match.group(1)):
            origins = [part.strip() for part in origin_text.split("/")]
            destinations = [part.strip() for part in destination_text.split("/")]
            for origin in origins:
                assert origin in declared_states, (statework_id, origin)
                for destination in destinations:
                    assert destination in declared_states, (statework_id, destination)
                    assert any(edge.get("from") in {origin, "*"}
                               and edge.get("to") == destination for edge in edges), (
                                   statework_id, origin, destination)
