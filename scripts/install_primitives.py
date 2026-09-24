"""Shared, symlink-resistant installer primitives.

Both StateWork installation entry points use this module.  The registry is a
host-owned directory; callers are responsible for choosing its trust boundary
and this module refuses to follow symlinks inside that boundary.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from pathlib import Path


class InstallSafetyError(RuntimeError):
    pass


class InstallJournal:
    """Rollback journal for one registry generation.

    The journal snapshots only paths the installer explicitly intends to
    replace.  It never follows a symlink in the managed registry.  A failed
    install restores those paths byte-for-byte; a successful install removes
    the journal after the ownership manifest is published.
    """

    def __init__(self, root: Path):
        self.root = assert_real_directory(Path(root))
        self._directory = Path(tempfile.mkdtemp(prefix=".installer-journal-",
                                                 dir=str(self.root)))
        self._snapshots: dict[Path, tuple[str, Path | None]] = {}
        self._closed = False

    def capture(self, path: Path) -> None:
        path = Path(path)
        assert_no_symlink_components(self.root, path)
        if path in self._snapshots:
            return
        info = _lstat(path)
        if info is None:
            self._snapshots[path] = ("missing", None)
            return
        if stat.S_ISLNK(info.st_mode):
            raise InstallSafetyError(f"refusing to journal symlink: {path}")
        name = str(len(self._snapshots))
        backup = self._directory / name
        if stat.S_ISDIR(info.st_mode):
            for nested in path.rglob("*"):
                if nested.is_symlink():
                    raise InstallSafetyError(f"refusing to journal symlink: {nested}")
            shutil.copytree(path, backup)
            self._snapshots[path] = ("directory", backup)
        elif stat.S_ISREG(info.st_mode):
            shutil.copy2(path, backup)
            self._snapshots[path] = ("file", backup)
        else:
            raise InstallSafetyError(f"unsupported managed path type: {path}")

    @staticmethod
    def _remove_current(path: Path) -> None:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)

    def rollback(self) -> None:
        if self._closed:
            return
        # Restore deepest paths first so a failed replacement cannot leave a
        # child from the failed generation inside an old directory.
        for path, (kind, backup) in sorted(
                self._snapshots.items(), key=lambda item: len(item[0].parts), reverse=True):
            assert_no_symlink_components(self.root, path)
            if path.exists() or path.is_symlink():
                self._remove_current(path)
            if kind == "missing":
                continue
            ensure_directory(self.root, path.parent)
            if kind == "file":
                shutil.copy2(backup, path)
            else:
                shutil.copytree(backup, path)
        shutil.rmtree(self._directory, ignore_errors=True)
        self._closed = True

    def commit(self) -> None:
        if self._closed:
            return
        shutil.rmtree(self._directory, ignore_errors=True)
        self._closed = True

    def __enter__(self) -> "InstallJournal":
        return self

    def __exit__(self, exc_type, _exc, _tb) -> bool:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False


def _lstat(path: Path):
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def assert_real_directory(path: Path, *, create: bool = False) -> Path:
    path = Path(path).expanduser()
    if create:
        # Create parents one component at a time; exist_ok alone can accept a
        # symlinked component.
        current = Path(path.anchor) if path.is_absolute() else Path()
        for component in path.parts[1:] if path.is_absolute() else path.parts:
            current = current / component
            info = _lstat(current)
            if info is None:
                current.mkdir()
                info = _lstat(current)
            if info is None or stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise InstallSafetyError(f"managed registry component is not a real directory: {current}")
    info = _lstat(path)
    if info is None or stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise InstallSafetyError(f"managed registry is not a real directory: {path}")
    return path


def assert_no_symlink_components(root: Path, path: Path, *, allow_leaf_missing: bool = True) -> Path:
    root = assert_real_directory(Path(root))
    path = Path(path)
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise InstallSafetyError(f"managed path escapes registry: {path}") from exc
    current = root
    parts = relative.parts
    for index, component in enumerate(parts):
        current = current / component
        info = _lstat(current)
        if info is None:
            if allow_leaf_missing or index < len(parts) - 1:
                continue
            raise InstallSafetyError(f"managed path is missing: {current}")
        if stat.S_ISLNK(info.st_mode):
            raise InstallSafetyError(f"managed path contains a symlink: {current}")
    return path


def ensure_directory(root: Path, destination: Path) -> Path:
    assert_no_symlink_components(root, destination)
    current = Path(root)
    for component in destination.relative_to(root).parts:
        current = current / component
        info = _lstat(current)
        if info is None:
            current.mkdir()
        elif stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise InstallSafetyError(f"managed directory is unsafe: {current}")
    return destination


def _check_destination(root: Path, destination: Path, *, kind: str = "file") -> None:
    assert_no_symlink_components(root, destination)
    info = _lstat(destination)
    if info is None:
        return
    if stat.S_ISLNK(info.st_mode):
        raise InstallSafetyError(f"refusing to overwrite symlink: {destination}")
    if kind == "file" and not stat.S_ISREG(info.st_mode):
        raise InstallSafetyError(f"refusing to overwrite non-file: {destination}")


def check_owned_overwrite(root: Path, destination: Path, relative: str,
                          previous_digests: dict[str, str], *,
                          allow_replace_modified: bool = False) -> None:
    """Fail closed on first-install collisions and modified managed files."""
    _check_destination(root, destination)
    if not destination.exists():
        return
    expected = previous_digests.get(relative)
    actual = hashlib.sha256(destination.read_bytes()).hexdigest()
    if expected is None:
        raise InstallSafetyError(
            f"existing unmanaged path collision: {relative}; explicit adoption required")
    if actual != expected and not allow_replace_modified:
        raise InstallSafetyError(
            f"managed path was modified since last install: {relative}; "
            "use --replace-modified-managed-files to replace it")


def copy_owned_file(source: Path, destination: Path, root: Path, relative: str,
                    previous_digests: dict[str, str], *,
                    allow_replace_modified: bool = False,
                    journal: InstallJournal | None = None) -> None:
    if not source.is_file() or source.is_symlink():
        raise InstallSafetyError(f"source artifact is not a regular file: {source}")
    ensure_directory(root, destination.parent)
    check_owned_overwrite(root, destination, relative, previous_digests,
                          allow_replace_modified=allow_replace_modified)
    if journal is not None:
        journal.capture(destination)
    fd, temporary = tempfile.mkstemp(dir=str(destination.parent), prefix=f".{destination.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream, source.open("rb") as source_stream:
            shutil.copyfileobj(source_stream, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(source.stat().st_mode) or 0o600)
        # Replacement replaces the destination entry itself, never follows a
        # destination symlink introduced after preflight.
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_owned_file(content: str, destination: Path, root: Path, relative: str,
                     previous_digests: dict[str, str], *,
                     allow_replace_modified: bool = False,
                     journal: InstallJournal | None = None) -> None:
    fd, temporary_source = tempfile.mkstemp(prefix="installer-source-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
        copy_owned_file(Path(temporary_source), destination, root, relative,
                        previous_digests, allow_replace_modified=allow_replace_modified,
                        journal=journal)
    finally:
        if os.path.exists(temporary_source):
            os.unlink(temporary_source)
