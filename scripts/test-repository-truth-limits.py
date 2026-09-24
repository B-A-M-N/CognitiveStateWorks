#!/usr/bin/env python3
"""Verify repository fingerprinting fails closed at resource limits."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("repository_truth", ROOT / "scripts" / "validate-repository-truth.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main() -> int:
    try:
        MODULE._bounded_subprocess(["python", "-c", "print('x' * 4096)"],
                                  output_limit=32, timeout=5)
    except MODULE.ResourceLimitError:
        print("REPOSITORY_TRUTH_LIMIT_TEST=PASS")
        return 0
    raise AssertionError("bounded subprocess accepted output over its configured budget")


if __name__ == "__main__":
    raise SystemExit(main())
