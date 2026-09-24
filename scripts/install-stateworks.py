#!/usr/bin/env python3
"""Install StateWorks into the runtime skill registry as self-contained
compact runtime capsules.

Deployment model: manifest-backed registered skills. The installed wrapper
embeds the StateWork's compact runtime capsule (runtime.md; falls back to a
generated capsule from the source entrypoint when absent) so the installed
artifact is self-contained and portable — it does NOT depend on a sibling
source checkout.

Install layout (per StateWork):

    <registry>/<name>/
      SKILL.md          compact self-contained runtime capsule
      manifest.yaml     copy of the source manifest
      fingerprint       sha256 of the source runtime capsule (doctor parity)

Wrappers are regenerable; never hand-edit them.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
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


def load_yaml(path: Path):
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def runtime_capsule(name: str) -> str:
    """The compact runtime capsule for a StateWork: runtime.md if present,
    else a minimal generated capsule. Self-contained; no source pointer."""
    capsule_path = ROOT / name / "runtime.md"
    if capsule_path.exists():
        return capsule_path.read_text(encoding="utf-8")
    # minimal generated capsule from the manifest + entrypoint frontmatter
    manifest_path = ROOT / name / "manifest.yaml"
    manifest = load_yaml(manifest_path) if manifest_path.exists() else {}
    return f"""# {name} — StateWork Runtime Capsule (generated)

Phase: {manifest.get('phase', 'domain_state')}
Requires: {', '.join(manifest.get('core_requirements', [])) or 'none'}
Consumes (required): {manifest.get('inputs', {}).get('required', []) or manifest.get('consumes', [])}
Emits: {', '.join(manifest.get('emits', [])) or 'none'}
Handoff: {manifest.get('handoff', '')}

Resolve the active flow, then load no more than two relevant specialists.
Emit the typed handoff packet in the common envelope before completion.
"""


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

    import yaml
    registry_path = ROOT / "registry.yaml"
    if not registry_path.exists():
        print("Missing registry.yaml")
        return 1
    registry = load_yaml(registry_path)
    names = registry.get("stateworks", [])
    missing = []
    for name in names:
        source_dir = ROOT / name
        manifest_path = source_dir / "manifest.yaml"
        source_skill = source_dir / "SKILL.md"
        if not source_skill.exists():
            source_skill = source_dir / "STATEWORK.md"
        if (not manifest_path.is_file() or manifest_path.is_symlink()
                or not source_skill.is_file() or source_skill.is_symlink()):
            missing.append(name)
    if missing:
        print("Missing mandatory StateWork artifacts: " + ", ".join(missing))
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
        for name in names:
            manifest_path = ROOT / name / "manifest.yaml"
            source_dir = ROOT / name
            source_skill = source_dir / "SKILL.md"
            if not source_skill.exists():
                source_skill = source_dir / "STATEWORK.md"
            if not manifest_path.is_file() or not source_skill.is_file():
                print(f"[FAIL] {name}: missing manifest or source skill")
                return 1
            dst_dir = reg / name
            if dst_dir.exists() and not any(item == name or item.startswith(name + "/")
                                            for item in previous):
                raise InstallSafetyError(f"first-install collision at {dst_dir}")
            ensure_directory(reg, dst_dir)
            _copy_args = dict(previous_digests=previous_digests,
                              allow_replace_modified=args.replace_modified_managed_files)
            copy_owned_file(source_skill, dst_dir / "SKILL.md", reg,
                            relative(reg, dst_dir / "SKILL.md"), journal=journal, **_copy_args)
            copy_owned_file(manifest_path, dst_dir / "manifest.yaml", reg,
                            relative(reg, dst_dir / "manifest.yaml"), journal=journal, **_copy_args)
            fingerprint = dst_dir / "fingerprint"
            relative_fingerprint = relative(reg, fingerprint)
            from install_primitives import write_owned_file as safe_write
            safe_write(sha256(source_skill) + "\n", fingerprint, reg,
                       relative_fingerprint, previous_digests,
                       allow_replace_modified=args.replace_modified_managed_files,
                       journal=journal)
            owned.update({relative(reg, dst_dir / "SKILL.md"),
                          relative(reg, dst_dir / "manifest.yaml"), relative_fingerprint})
            print(f"  [ok]   {name} -> {dst_dir}")
            installed += 1
        if args.enforcing_runtime:
            enforcing = reg / "cognitive_statework_runtime"
            journal.capture(enforcing)
            ensure_directory(reg, enforcing)
            source_runtime = ROOT / "scripts" / "control_plane.py"
            destination_runtime = enforcing / "control_plane.py"
            copy_owned_file(source_runtime, destination_runtime, reg,
                                  relative(reg, destination_runtime), previous_digests,
                                  allow_replace_modified=args.replace_modified_managed_files,
                                  journal=journal)
            owned.add(relative(reg, destination_runtime))
            for schema_name in ("packet-registry.yaml", "evidence-kinds.yaml",
                                "packet-registry.schema.json", "evidence-kinds.schema.json",
                                "handoff-packet.schema.json", "statework-flow.schema.json",
                                "transition-contract.schema.json", "statework-manifest.schema.json"):
                source_schema = ROOT / "schemas" / schema_name
                if not source_schema.exists():
                    continue
                destination_schema = enforcing / "schemas" / schema_name
                copy_owned_file(source_schema, destination_schema, reg,
                                      relative(reg, destination_schema), previous_digests,
                                      allow_replace_modified=args.replace_modified_managed_files,
                                      journal=journal)
                owned.add(relative(reg, destination_schema))
            interface = enforcing / "host-interface.json"
            from install_primitives import write_owned_file as safe_write
            safe_write(json.dumps({
                "runtime_version": "1.0.0",
                "operations": ["resolve_statework", "start_or_resume_subject",
                                "submit_attested_observation", "request_transition",
                                "publish_packet", "recover_from_invalidation"],
                "authority": "SubjectStateStore owns current state; EvidenceStore resolves references",
            }, indent=2) + "\n", interface, reg, relative(reg, interface), previous_digests,
                allow_replace_modified=args.replace_modified_managed_files, journal=journal)
            owned.add(relative(reg, interface))
            validator_source = ROOT / "scripts" / "validate-repository-truth.py"
            validator_destination = enforcing / "validate-repository-truth.py"
            copy_owned_file(validator_source, validator_destination, reg,
                             relative(reg, validator_destination), previous_digests,
                             allow_replace_modified=args.replace_modified_managed_files,
                             journal=journal)
            owned.add(relative(reg, validator_destination))
            validator_schema = ROOT / "schemas" / "repository-truth-packet.schema.json"
            validator_schema_destination = enforcing / "schemas" / "repository-truth-packet.schema.json"
            copy_owned_file(validator_schema, validator_schema_destination, reg,
                            relative(reg, validator_schema_destination), previous_digests,
                            allow_replace_modified=args.replace_modified_managed_files,
                            journal=journal)
            owned.add(relative(reg, validator_schema_destination))
            enforcing_registry = enforcing / "registry.yaml"
            copy_owned_file(ROOT / "registry.yaml", enforcing_registry, reg,
                                  relative(reg, enforcing_registry), previous_digests,
                                  allow_replace_modified=args.replace_modified_managed_files,
                                  journal=journal)
            owned.add(relative(reg, enforcing_registry))
            for statework_name in names:
                source_statework = ROOT / statework_name
                destination_statework = enforcing / statework_name
                ensure_directory(reg, destination_statework)
                for artifact_name in ("manifest.yaml", "transitions.yaml", "runtime.md",
                                      "SKILL.md", "STATEWORK.md"):
                    source_artifact = source_statework / artifact_name
                    if not source_artifact.exists():
                        continue
                    destination_artifact = destination_statework / artifact_name
                    copy_owned_file(source_artifact, destination_artifact, reg,
                                          relative(reg, destination_artifact), previous_digests,
                                          allow_replace_modified=args.replace_modified_managed_files,
                                          journal=journal)
                    owned.add(relative(reg, destination_artifact))
                flows_source = source_statework / "flows"
                if flows_source.is_dir():
                    for flow_file in sorted(flows_source.rglob("*")):
                        if not flow_file.is_file():
                            continue
                        destination_flow = destination_statework / flow_file.relative_to(source_statework)
                        ensure_directory(reg, destination_flow.parent)
                        copy_owned_file(flow_file, destination_flow, reg,
                                              relative(reg, destination_flow), previous_digests,
                                              allow_replace_modified=args.replace_modified_managed_files,
                                              journal=journal)
                        owned.add(relative(reg, destination_flow))
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
