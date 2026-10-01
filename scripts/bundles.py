"""Safe file access and hashing for data-only StateWork bundles."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

try:
    from .control_plane import TransitionError
except ImportError:
    from control_plane import TransitionError


class BundleFiles:
    """Resolve only regular files contained by a declared bundle root."""

    @staticmethod
    def relative_file(bundle_root: Path, name: str) -> Path:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise TransitionError(f"bundle contract path escapes its owner: {name!r}")
        bundle_root = Path(bundle_root)
        if bundle_root.is_symlink():
            raise TransitionError("StateWork bundle root cannot be a symlink")
        candidate = bundle_root / path
        current = candidate
        while current != bundle_root:
            if current.is_symlink():
                raise TransitionError(f"bundle contract path contains a symlink: {name!r}")
            current = current.parent
        resolved = candidate.resolve()
        try:
            resolved.relative_to(bundle_root.resolve())
        except ValueError as exc:
            raise TransitionError(f"bundle contract path escapes its owner: {name!r}") from exc
        if not resolved.is_file() or resolved.is_symlink():
            raise TransitionError(f"bundle contract file is missing or linked: {name!r}")
        return resolved

    @staticmethod
    def hashes(bundle_root: Path) -> dict[str, str]:
        if bundle_root.is_symlink():
            raise TransitionError("StateWork bundle root cannot be a symlink")
        result: dict[str, str] = {}
        for path in sorted(bundle_root.rglob("*")):
            if path.is_symlink():
                raise TransitionError(f"StateWork bundles cannot contain symlinks: {path}")
            if path.is_file():
                result[path.relative_to(bundle_root).as_posix()] = hashlib.sha256(
                    path.read_bytes()).hexdigest()
        return result


__all__ = ["BundleFiles"]
