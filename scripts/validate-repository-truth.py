#!/usr/bin/env python3
"""Compatibility CLI for the importable repository-truth validator."""
from __future__ import annotations

import sys

if __package__:
    from . import repository_truth as _implementation
else:
    import repository_truth as _implementation


def __getattr__(name: str):
    """Keep historical direct-script test imports working during migration."""
    return getattr(_implementation, name)


def main() -> int:
    return _implementation.main()


if __name__ == "__main__":
    sys.exit(main())
