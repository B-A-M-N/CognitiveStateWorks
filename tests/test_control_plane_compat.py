from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import control_plane
from scripts import errors, evidence, resources


def test_control_plane_reexports_extracted_evidence_and_resource_api():
    assert control_plane.TransitionError is errors.TransitionError
    assert control_plane.PacketValidationError is errors.PacketValidationError
    assert control_plane.EvidenceStore is evidence.EvidenceStore
    assert control_plane.TrustedValidatorRegistry is evidence.TrustedValidatorRegistry
    assert control_plane.FreshnessValidatorRegistry is evidence.FreshnessValidatorRegistry
    assert control_plane.EvidenceValidatorRegistry is evidence.EvidenceValidatorRegistry
    assert control_plane.FRESHNESS_VALIDATORS is evidence.FRESHNESS_VALIDATORS
    assert control_plane.EVIDENCE_VALIDATORS is evidence.EVIDENCE_VALIDATORS
    assert control_plane.evaluate_freshness is evidence.evaluate_freshness
    assert control_plane._aware_datetime is resources._aware_datetime
    assert control_plane.load_evidence_kind_registry is resources.load_evidence_kind_registry
    assert control_plane.load_packet_registry is resources.load_packet_registry
    assert control_plane.render_runtime_capsule is resources.render_runtime_capsule


def test_control_plane_lazy_registry_compiler_compatibility():
    assert control_plane.RegistryCompiler.__module__ == "scripts.registry"
    with pytest.raises(AttributeError, match="unknown_compat_name"):
        control_plane.unknown_compat_name


def test_direct_script_import_reexports_extracted_api():
    check = """
import control_plane
import errors
import evidence
import resources
assert control_plane.EvidenceStore is evidence.EvidenceStore
assert control_plane.TransitionError is errors.TransitionError
assert control_plane.evaluate_freshness is evidence.evaluate_freshness
assert control_plane._schema_text is resources._schema_text
assert control_plane.RegistryCompiler.__module__ == 'registry'
"""
    result = subprocess.run(
        [sys.executable, "-c", check], cwd=ROOT / "scripts", text=True,
        capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
