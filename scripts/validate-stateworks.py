#!/usr/bin/env python3
"""Command-line wrapper for the shared StateWork validation library."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validation import validate_stateworks


if __name__ == "__main__":
    raise SystemExit(validate_stateworks())
