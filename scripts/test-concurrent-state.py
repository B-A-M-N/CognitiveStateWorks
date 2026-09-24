#!/usr/bin/env python3
"""Concurrency and caller-directory safety checks for PacketStore."""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from scripts.control_plane import PacketStore, PacketValidationError


def main() -> int:
    fixture = json.loads((ROOT / "fixtures" / "fixtures-valid.ndjson").read_text().splitlines()[0])
    with tempfile.TemporaryDirectory(prefix="statework-concurrency-") as raw:
        root = Path(raw)
        storage = root / "store.json"
        first = copy.deepcopy(fixture)
        second = copy.deepcopy(fixture)
        first["packet_id"] = "concurrent-a"
        second["packet_id"] = "concurrent-b"
        a = PacketStore(packet_registry_path=ROOT / "schemas" / "packet-registry.yaml",
                        storage_path=storage)
        b = PacketStore(packet_registry_path=ROOT / "schemas" / "packet-registry.yaml",
                        storage_path=storage)
        a.put(first)
        try:
            b.put(second)
        except PacketValidationError:
            assert b.get("concurrent-b") is None
            b.reload()
        else:
            raise AssertionError("stale writer unexpectedly committed")
        assert a.get("concurrent-a") is not None
        parent = root / "caller-owned"
        parent.mkdir()
        mode_before = parent.stat().st_mode
        PacketStore(packet_registry_path=ROOT / "schemas" / "packet-registry.yaml",
                    storage_path=parent / "store.json")
        assert parent.stat().st_mode == mode_before
    print("CONCURRENT_STATE_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
