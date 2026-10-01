from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.workflow_engines import EngineRegistry
from scripts.control_plane import (EvidenceStore, EvidenceValidatorRegistry,
                                   FreshnessValidatorRegistry, TransitionError)


class _PluginEngine:
    kind = "demo"
    contract_version = "demo/v1"

    def validate_contract(self, contract):
        return None

    def initialize(self, identity, contract):
        return {}

    def inspect(self, identity, contract, state, revision):
        return None

    def eligible_steps(self, identity, contract, snapshot):
        return ()

    def apply(self, identity, contract, snapshot, *, step_id, evidence):
        return None


class _Distribution:
    metadata = {"Name": "demo-workflow-plugin"}
    version = "1.2.3"

    def __init__(self, root: Path):
        self.root = root
        self.files = [Path("demo_engine.py")]

    def locate_file(self, path: Path) -> Path:
        return self.root / path


class _EntryPoint:
    name = "demo"
    value = "demo_engine:DemoEngine"

    def __init__(self, distribution: _Distribution):
        self.dist = distribution
        self.load_count = 0
        self.implementation = _PluginEngine

    def load(self):
        self.load_count += 1
        return self.implementation


def _fixture(tmp_path: Path) -> tuple[_EntryPoint, str, str]:
    source = tmp_path / "demo_engine.py"
    source.write_text("class DemoEngine: ...\n", encoding="utf-8")
    entry_point = _EntryPoint(_Distribution(tmp_path))
    identity = EngineRegistry.entry_point_identity(entry_point)
    digest = EngineRegistry.entry_point_source_hash(entry_point)
    return entry_point, identity, digest


def test_engine_entry_point_load_requires_an_explicit_source_pin(tmp_path: Path):
    entry_point, identity, digest = _fixture(tmp_path)
    registry = EngineRegistry()

    loaded = registry._load_entries({identity: digest}, [entry_point])

    assert loaded == ("demo",)
    assert registry.identities["demo"] == digest
    assert entry_point.load_count == 1


def test_engine_entry_point_hash_is_checked_before_import(tmp_path: Path):
    entry_point, identity, _digest = _fixture(tmp_path)
    registry = EngineRegistry()

    with pytest.raises(PermissionError, match="trust pin"):
        registry._load_entries({identity: "0" * 64}, [entry_point])

    assert entry_point.load_count == 0


def test_unadopted_engine_entry_points_are_not_imported(tmp_path: Path):
    entry_point, _identity, _digest = _fixture(tmp_path)
    registry = EngineRegistry()

    assert registry._load_entries({}, [entry_point]) == ()
    assert entry_point.load_count == 0


def test_freshness_validator_entry_point_uses_the_same_explicit_pin(tmp_path: Path):
    entry_point, _identity, _digest = _fixture(tmp_path)
    entry_point.name = "freshness_check"
    entry_point.implementation = lambda packet, context: packet.get("fresh") is True
    identity = EngineRegistry.entry_point_identity(entry_point)
    digest = EngineRegistry.entry_point_source_hash(entry_point)
    validators = FreshnessValidatorRegistry()

    assert validators._load_entries({identity: digest}, [entry_point]) == (
        "freshness_check",)
    assert validators.validate("freshness_check", {"fresh": True}, {})
    assert not validators.validate("freshness_check", {"fresh": False}, {})


def test_registered_evidence_validator_runs_before_evidence_is_attested():
    validators = EvidenceValidatorRegistry()
    validators.register("evidence_check", lambda record, _context: record.get("valid") is True,
                        implementation_hash="a" * 64, trusted=True)
    store = EvidenceStore(validator_registry=validators)

    with pytest.raises(TransitionError, match="rejected"):
        store.create({"ref": "rejected", "kind": "custom",
                      "validator": "evidence_check", "valid": False})
    assert store.create({"ref": "accepted", "kind": "custom",
                         "validator": "evidence_check", "valid": True}) == "accepted"
