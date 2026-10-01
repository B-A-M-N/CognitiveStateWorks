from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.bundles import BundleFiles
from scripts.control_plane import TransitionError


def test_bundle_file_access_rejects_symlinked_contracts(tmp_path: Path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.write_text("contracts: {}\n", encoding="utf-8")
    (bundle / "contracts.yaml").symlink_to(outside)

    with pytest.raises(TransitionError, match="symlink"):
        BundleFiles.relative_file(bundle, "contracts.yaml")


def test_bundle_hash_rejects_symlinked_members(tmp_path: Path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    (bundle / "linked.txt").symlink_to(outside)

    with pytest.raises(TransitionError, match="symlinks"):
        BundleFiles.hashes(bundle)
