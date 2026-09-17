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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REGISTRIES = {
    "agents": Path.home() / ".agents" / "skills",
    "codex": Path.home() / ".codex" / "skills",
}


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", nargs="+", default=None,
                        choices=list(REGISTRIES), help="registries to install into")
    parser.add_argument("--registry", action="append", default=[], metavar="NAME=PATH",
                        help="arbitrary host registry; repeatable")
    args = parser.parse_args()

    import yaml
    registry_path = ROOT / "registry.yaml"
    if not registry_path.exists():
        print("Missing registry.yaml")
        return 1
    registry = load_yaml(registry_path)
    names = registry.get("stateworks", [])

    selected_targets = args.target if args.target is not None else (
        [] if args.registry else ["agents"])
    try:
        target_specs = registry_specs(selected_targets, args.registry)
    except ValueError as exc:
        parser.error(str(exc))

    installed_any = False
    for target, reg in target_specs:
        try:
            reg.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"[SKIP] {target}: cannot create registry {reg}: {exc}")
            continue
        if not os.access(reg, os.W_OK):
            print(f"[SKIP] {target}: registry {reg} is not writable")
            continue
        reg.mkdir(parents=True, exist_ok=True)
        print(f"Installing into {reg}")
        installed = 0
        for name in names:
            manifest_path = ROOT / name / "manifest.yaml"
            if not manifest_path.exists():
                print(f"  [SKIP] {name}: no manifest.yaml")
                continue
            manifest = load_yaml(manifest_path)
            dst_dir = reg / name
            dst_dir.mkdir(parents=True, exist_ok=True)
            capsule = runtime_capsule(name)
            wrapper = f"""---
name: {name}
description: >
  Self-contained runtime capsule for the {name} StateWork (generated by
  scripts/install-stateworks.py — do not hand-edit). Embeds the compact
  runtime protocol; does not require the source checkout.
---

{capsule}
"""
            (dst_dir / "SKILL.md").write_text(wrapper, encoding="utf-8")
            shutil.copy2(manifest_path, dst_dir / "manifest.yaml")
            (dst_dir / "fingerprint").write_text(sha256(ROOT / name / "runtime.md") + "\n"
                                                 if (ROOT / name / "runtime.md").exists()
                                                 else sha256(ROOT / name / "SKILL.md") + "\n")
            print(f"  [ok]   {name} -> {dst_dir}")
            installed += 1
        print(f"  installed {installed} wrapper(s) into {reg}")
        installed_any = installed_any or installed > 0

    print("\nRun ../CognitiveFrameWorks/scripts/doctor.py to verify routability.")
    return 0 if installed_any else 1


if __name__ == "__main__":
    sys.exit(main())
