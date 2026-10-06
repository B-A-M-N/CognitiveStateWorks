from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.registry import RegistryCompiler


def test_builtin_engine_hashes_pin_semantic_sources_separately_from_facades():
    manifest = RegistryCompiler.BUILTIN_ENGINE_SOURCE_MANIFEST

    assert "transition_engine.py" in manifest["state_machine"]
    assert "evidence.py" in manifest["state_machine"]
    assert "flow_selectors.py" in manifest["flow_selector"]
    assert all("control_plane.py" not in files for files in manifest.values())
    assert len(RegistryCompiler._registry_compiler_hash()) == 64
    assert len(RegistryCompiler._compatibility_api_hash()) == 64
