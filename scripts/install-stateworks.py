#!/usr/bin/env python3
"""Install compiled StateWork bundles and their generated runtime capsules."""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
from install_primitives import (InstallSafetyError, assert_no_symlink_components,
                                assert_real_directory, copy_owned_file,
                                ensure_directory, write_owned_file, InstallJournal)

REGISTRIES = {
    "agents": Path.home() / ".agents" / "skills",
    "codex": Path.home() / ".codex" / "skills",
}

MANIFEST_NAME = ".cognitiveframeworks-csw-managed.json"
MANIFEST_VERSION = 1
_ACTIVE_JOURNALS: list[InstallJournal] = []


def registry_specs(targets: list[str] | None, custom: list[str]) -> list[tuple[str, Path]]:
    selected = list(targets or [])
    specs = [(name, REGISTRIES[name]) for name in selected]
    for raw in custom:
        if "=" in raw:
            name, value = raw.split("=", 1)
        else:
            value = raw
            name = Path(value).expanduser().name or "custom"
        if not name or not value:
            raise ValueError(f"invalid --registry {raw!r}; expected NAME=PATH")
        specs.append((name, Path(value).expanduser()))
    deduped: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for name, path in specs:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append((name, path))
    return deduped


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(registry: Path, path: Path) -> str:
    return path.relative_to(registry).as_posix()


def load_owned(registry: Path) -> tuple[set[str], dict[str, str], str | None]:
    assert_real_directory(registry)
    manifest = registry / MANIFEST_NAME
    if not manifest.exists() and not manifest.is_symlink():
        return set(), {}, None
    if manifest.is_symlink():
        raise InstallSafetyError(f"refusing symlinked ownership manifest: {manifest}")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("schema_version") != MANIFEST_VERSION or not isinstance(data.get("managed_paths"), list):
        raise InstallSafetyError("invalid shared ownership manifest")
    owned = set()
    for value in data["managed_paths"]:
        candidate = Path(str(value))
        if candidate.is_absolute() or ".." in candidate.parts:
            raise InstallSafetyError(f"unsafe managed path: {value!r}")
        assert_no_symlink_components(registry, registry / candidate)
        owned.add(candidate.as_posix())
    digests = data.get("managed_digests", {})
    if not isinstance(digests, dict):
        raise InstallSafetyError("invalid shared ownership digests")
    return owned, {str(k): str(v) for k, v in digests.items()}, data.get("installer")


def write_owned(registry: Path, paths: set[str]) -> None:
    payload = {
        "schema_version": MANIFEST_VERSION,
        "installer": "CognitiveStateWork",
        "managed_paths": sorted(paths),
        "managed_digests": {
            item: sha256(registry / item)
            for item in paths
            if (registry / item).is_file() and not (registry / item).is_symlink()
        },
    }
    fd, temporary = tempfile.mkstemp(dir=str(registry), prefix=f".{MANIFEST_NAME}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, registry / MANIFEST_NAME)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _main_impl() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", nargs="+", default=None,
                        choices=list(REGISTRIES), help="registries to install into")
    parser.add_argument("--registry", action="append", default=[], metavar="NAME=PATH",
                        help="arbitrary host registry; repeatable")
    parser.add_argument("--replace-modified-managed-files", action="store_true",
                        help="allow replacing managed files changed since the prior install")
    parser.add_argument("--enforcing-runtime", action="store_true",
                        help="also install the executable CSW controller and schemas")
    args = parser.parse_args()

    try:
        from registry import RegistryCompiler, load_compiled_registry
        compiled = load_compiled_registry(ROOT, verify_bundles=True)
    except Exception as exc:
        print(f"Invalid compiled StateWork registry: {exc}")
        return 1
    bundles = list(compiled.get("stateworks") or ())
    names = [str(item.get("id") or "") for item in bundles]
    if not names or any(not name for name in names) or len(names) != len(set(names)):
        print("Compiled StateWork registry has missing or duplicate bundle IDs")
        return 1

    selected_targets = args.target if args.target is not None else (
        [] if args.registry else ["agents"])
    try:
        target_specs = registry_specs(selected_targets, args.registry)
    except ValueError as exc:
        parser.error(str(exc))

    installed_any = False
    for target, reg in target_specs:
        try:
            assert_real_directory(reg, create=True)
        except (OSError, InstallSafetyError) as exc:
            print(f"[SKIP] {target}: cannot create registry {reg}: {exc}")
            continue
        if not os.access(reg, os.W_OK):
            print(f"[SKIP] {target}: registry {reg} is not writable")
            continue
        print(f"Installing into {reg}")
        previous, previous_digests, owner = load_owned(reg)
        if owner not in (None, "CognitiveStateWork"):
            print(f"[FAIL] {target}: registry is owned by {owner}; refusing collision")
            return 1
        journal = InstallJournal(reg)
        _ACTIVE_JOURNALS.append(journal)
        journal.capture(reg / MANIFEST_NAME)
        for relative_path in previous:
            journal.capture(reg / relative_path)
        installed = 0
        owned: set[str] = set()
        for bundle in bundles:
            name = str(bundle["id"])
            source_dir = Path(str(bundle["bundle_root"]))
            manifest = dict(bundle.get("manifest") or {})
            dst_dir = reg / name
            if dst_dir.exists() and not any(item == name or item.startswith(name + "/")
                                            for item in previous):
                raise InstallSafetyError(f"first-install collision at {dst_dir}")
            ensure_directory(reg, dst_dir)
            _copy_args = dict(previous_digests=previous_digests,
                              allow_replace_modified=args.replace_modified_managed_files)
            file_hashes = dict(bundle.get("file_hashes") or {})
            for bundle_path in sorted(file_hashes):
                source = source_dir / bundle_path
                destination = dst_dir / bundle_path
                ensure_directory(reg, destination.parent)
                copy_owned_file(source, destination, reg, relative(reg, destination),
                                journal=journal, **_copy_args)
                owned.add(relative(reg, destination))
            advisory_entrypoint = manifest.get("advisory_entrypoint")
            if advisory_entrypoint:
                source = (source_dir / str(advisory_entrypoint)).resolve()
                try:
                    source.relative_to(source_dir.resolve())
                except ValueError as exc:
                    raise InstallSafetyError(
                        f"{name}: advisory entrypoint escapes its bundle") from exc
                if not source.is_file() or source.is_symlink():
                    raise InstallSafetyError(f"{name}: advisory entrypoint is unavailable")
                skill = dst_dir / "SKILL.md"
                if source != skill:
                    # The advisory entrypoint is usually already installed as
                    # part of the bundle files (e.g. advisory SKILL.md); the
                    # safety check rejects rewriting an unmanaged path, so skip
                    # the copy when this run already wrote identical bytes.
                    if not (relative(reg, skill) in owned
                            and sha256(source) == sha256(skill)):
                        copy_owned_file(source, skill, reg, relative(reg, skill),
                                        journal=journal, **_copy_args)
                owned.add(relative(reg, skill))
            capsule = str(bundle.get("runtime_capsule") or "")
            capsule_path = dst_dir / "RUNTIME.md"
            write_owned_file(capsule, capsule_path, reg, relative(reg, capsule_path),
                             previous_digests,
                             allow_replace_modified=args.replace_modified_managed_files,
                             journal=journal)
            owned.add(relative(reg, capsule_path))
            print(f"  [ok]   {name} -> {dst_dir}")
            installed += 1
        if args.enforcing_runtime:
            enforcing = reg / "cognitive_statework_runtime"
            journal.capture(enforcing)
            ensure_directory(reg, enforcing)
            _copy_args = dict(previous_digests=previous_digests,
                              allow_replace_modified=args.replace_modified_managed_files,
                              journal=journal)
            for source in sorted((ROOT / "scripts").rglob("*.py")):
                if (source.is_symlink() or "__pycache__" in source.parts
                        or source.name.startswith("test-")):
                    continue
                destination = enforcing / source.relative_to(ROOT / "scripts")
                ensure_directory(reg, destination.parent)
                copy_owned_file(source, destination, reg, relative(reg, destination),
                                **_copy_args)
                owned.add(relative(reg, destination))
            for source in sorted((ROOT / "schemas").rglob("*")):
                if source.is_dir() or source.is_symlink():
                    continue
                destination = enforcing / "schemas" / source.relative_to(ROOT / "schemas")
                ensure_directory(reg, destination.parent)
                copy_owned_file(source, destination, reg, relative(reg, destination),
                                **_copy_args)
                owned.add(relative(reg, destination))
            interface = enforcing / "host-interface.json"
            write_owned_file(json.dumps({
                "runtime_version": "1.0.0",
                "operations": ["resolve_statework", "start_or_resume_subject",
                                "submit_attested_observation", "request_transition",
                                "publish_packet", "recover_from_invalidation"],
                "authority": "SubjectStateStore owns current state; EvidenceStore resolves references",
            }, indent=2) + "\n", interface, reg, relative(reg, interface), previous_digests,
                allow_replace_modified=args.replace_modified_managed_files, journal=journal)
            owned.add(relative(reg, interface))
            enforcing_registry = enforcing / "registry.yaml"
            registry_text = "version: 2.0.0\nstateworks:\n" + "".join(
                f"  - {json.dumps(name)}\n" for name in names)
            registry_text += "extension_roots: []\n"
            write_owned_file(registry_text, enforcing_registry, reg,
                             relative(reg, enforcing_registry), previous_digests,
                             allow_replace_modified=args.replace_modified_managed_files,
                             journal=journal)
            owned.add(relative(reg, enforcing_registry))
            for bundle in bundles:
                name = str(bundle["id"])
                source_root = Path(str(bundle["bundle_root"]))
                destination_root = enforcing / name
                for bundle_path in sorted(dict(bundle.get("file_hashes") or {})):
                    source = source_root / bundle_path
                    destination = destination_root / bundle_path
                    ensure_directory(reg, destination.parent)
                    copy_owned_file(source, destination, reg, relative(reg, destination),
                                    **_copy_args)
                    owned.add(relative(reg, destination))
            compiled_runtime = RegistryCompiler(enforcing).compile(write=False)
            compiled_path = enforcing / "compiled-registry.json"
            write_owned_file(json.dumps(compiled_runtime, sort_keys=True, indent=2) + "\n",
                             compiled_path, reg, relative(reg, compiled_path),
                             previous_digests,
                             allow_replace_modified=args.replace_modified_managed_files,
                             journal=journal)
            owned.add(relative(reg, compiled_path))
            print(f"  [ok]   enforcing runtime -> {enforcing}")
        print(f"  installed {installed} wrapper(s) into {reg}")
        stale = previous - owned
        for item in sorted(stale, reverse=True):
            path = reg / item
            if path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == previous_digests.get(item):
                path.unlink()
        write_owned(reg, owned)
        journal.commit()
        _ACTIVE_JOURNALS.remove(journal)
        installed_any = installed_any or installed > 0

    print("\nInstalled advisory skill capsules; use --enforcing-runtime for the executable CSW controller.")
    return 0 if installed_any else 1


def main() -> int:
    try:
        return _main_impl()
    except BaseException:
        for journal in reversed(_ACTIVE_JOURNALS):
            journal.rollback()
        _ACTIVE_JOURNALS.clear()
        raise


if __name__ == "__main__":
    sys.exit(main())
