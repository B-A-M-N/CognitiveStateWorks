from __future__ import annotations

from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_packaged_builtin_catalog_tracks_checkout_builtins():
    checkout = yaml.safe_load((ROOT / "registry.yaml").read_text(encoding="utf-8"))
    packaged = yaml.safe_load(
        (ROOT / "scripts" / "builtin" / "registry.yaml").read_text(encoding="utf-8"))

    assert packaged["version"] == checkout["version"]
    assert packaged["stateworks"] == checkout["stateworks"]
    assert "extension_roots" not in packaged
    assert all((ROOT / statework).is_dir() for statework in packaged["stateworks"])
