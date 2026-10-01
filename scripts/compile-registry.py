#!/usr/bin/env python3
"""Compile trusted StateWork bundles into the immutable runtime registry."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from registry import RegistryCompiler


def main() -> int:
    result = RegistryCompiler(ROOT).compile(write=True)
    print(f"Compiled {len(result['stateworks'])} StateWorks")
    print(f"Registry hash: {result['registry_hash']}")
    print(f"Artifact: {ROOT / 'compiled-registry.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
