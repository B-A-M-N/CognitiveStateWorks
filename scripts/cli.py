"""Installed command-line entry points for CognitiveStateWorks."""
from __future__ import annotations

from .control_plane import ROOT
from .registry import RegistryCompiler


def compile_registry() -> int:
    result = RegistryCompiler().compile(write=True)
    print(f"Compiled {len(result['stateworks'])} StateWorks")
    print(f"Registry hash: {result['registry_hash']}")
    print(f"Artifact: {ROOT / 'compiled-registry.json'}")
    return 0


__all__ = ["compile_registry"]
