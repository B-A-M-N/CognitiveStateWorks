"""Entrypoints must resolve to a file inside their owning bundle.

Root-relative entrypoints such as ``testworks/SKILL.md`` used to validate
by accident: ``scripts/validation.py`` fell back to resolving them against
the repo root, which only works because the source checkout nests every
bundle under the repo root. A relocated bundle cannot rely on that layout,
so the fallback is gone and the entrypoint must name a regular file inside
its own bundle directory.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.bundles import BundleFiles
from scripts.control_plane import TransitionError


def _registry_statework_ids() -> list[str]:
    with open(ROOT / "registry.yaml", encoding="utf-8") as fh:
        return list(yaml.safe_load(fh).get("stateworks", []))


def _manifest_entrypoint(statework_id: str) -> str:
    with open(ROOT / statework_id / "manifest.yaml", encoding="utf-8") as fh:
        return str(yaml.safe_load(fh).get("entrypoint") or "")


# Manifests owned by sibling slices whose entrypoints are still
# root-relative. Non-strict xfail keeps the suite green until those slices
# land, at which point these markers are removed.
PENDING_BUNDLE_LOCAL = frozenset()


def _entrypoint_params() -> list:
    params = []
    for statework_id in _registry_statework_ids():
        if statework_id in PENDING_BUNDLE_LOCAL:
            params.append(pytest.param(
                statework_id,
                marks=pytest.mark.xfail(
                    strict=False,
                    reason=(f"sibling slice owns {statework_id}/manifest.yaml; "
                            "entrypoint still root-relative"),
                ),
            ))
        else:
            params.append(pytest.param(statework_id))
    return params


@pytest.mark.parametrize("statework_id", _entrypoint_params())
def test_statework_entrypoint_resolves_bundle_locally(statework_id: str) -> None:
    bundle_root = ROOT / statework_id
    entrypoint = _manifest_entrypoint(statework_id)
    assert entrypoint, f"{statework_id}: manifest declares no entrypoint"
    resolved = BundleFiles.relative_file(bundle_root, entrypoint)
    assert resolved.is_file() and not resolved.is_symlink()


def test_testworks_entrypoint_is_bundle_local() -> None:
    assert _manifest_entrypoint("testworks") == "SKILL.md"


def test_root_relative_entrypoint_rejected_despite_file_under_root() -> None:
    # The old repo-root fallback accepted this value because the checkout
    # nests bundles under the repo root; bundle-local resolution rejects it.
    assert (ROOT / "testworks" / "SKILL.md").is_file()
    with pytest.raises(TransitionError):
        BundleFiles.relative_file(ROOT / "testworks", "testworks/SKILL.md")


def test_entrypoint_resolution_rejects_absolute_and_parent_traversal() -> None:
    bundle_root = ROOT / "testworks"
    with pytest.raises(TransitionError):
        BundleFiles.relative_file(bundle_root, "/etc/hostname")
    with pytest.raises(TransitionError):
        BundleFiles.relative_file(bundle_root, "../godkiller/SKILL.md")


def test_testworks_resolves_in_isolated_layout_outside_checkout(
        tmp_path: Path) -> None:
    """A copy of testworks outside the checkout must stand alone.

    Proves the source-checkout layout no longer masks the defect: the fixed
    bundle-local entrypoint resolves in isolation while the old
    root-relative value does not.
    """
    isolated = tmp_path / "relocated" / "testworks"
    shutil.copytree(ROOT / "testworks", isolated, symlinks=False)
    with pytest.raises(ValueError):
        isolated.resolve().relative_to(ROOT.resolve())

    entrypoint = _manifest_entrypoint("testworks")
    resolved = BundleFiles.relative_file(isolated, entrypoint)
    assert resolved.is_file() and not resolved.is_symlink()

    with pytest.raises(TransitionError):
        BundleFiles.relative_file(isolated, "testworks/SKILL.md")
