#!/usr/bin/env python3
"""Create a schema-valid starter StateWork bundle under extensions/."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    from .registry import RegistryCompiler
except ImportError:
    from registry import RegistryCompiler


_SCRIPT_ROOT = Path(__file__).resolve().parent
ROOT = (_SCRIPT_ROOT if (_SCRIPT_ROOT / "registry.yaml").is_file()
        else _SCRIPT_ROOT.parent)
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
DOMAIN_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def _write_yaml(path: Path, value: Any) -> None:
    path.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True),
                    encoding="utf-8")


def scaffold(*, bundle_id: str, domain: str, purpose: str,
             engine_kind: str = "state_machine", root: Path = ROOT,
             name: str | None = None) -> Path:
    if not ID_PATTERN.fullmatch(bundle_id):
        raise ValueError("id must use 1-64 lowercase letters, numbers, '_' or '-'")
    if not DOMAIN_PATTERN.fullmatch(domain):
        raise ValueError("domain must be a lowercase identifier with at least two characters")
    if not isinstance(purpose, str) or not 12 <= len(purpose.strip()) <= 240:
        raise ValueError("purpose must contain 12-240 non-space characters")
    if engine_kind not in {"state_machine", "milestone"}:
        raise ValueError("engine must be state_machine or milestone")

    root = Path(root).resolve()
    extension_root = root / "extensions"
    if extension_root.is_symlink() or not extension_root.is_dir():
        raise ValueError("trusted extensions/ directory is missing or linked")
    bundle_root = extension_root / bundle_id
    if bundle_root.exists() or bundle_root.is_symlink():
        raise FileExistsError(f"StateWork destination already exists: {bundle_root}")
    bundle_root.mkdir(mode=0o755)
    display_name = name or bundle_id.replace("_", " ").replace("-", " ").title()
    contract_name = "transitions.yaml" if engine_kind == "state_machine" else "milestones.yaml"
    contract_version = "state-machine/v1" if engine_kind == "state_machine" else "milestone/v1"
    manifest = {
        "id": bundle_id,
        "domain": domain,
        "purpose": purpose.strip(),
        "name": display_name,
        "entrypoint": "README.md",
        "advisory_entrypoint": "README.md",
        "triggers": [domain.replace("_", " ")],
        "match": {"required_any": [domain.replace("_", " ")], "secondary": []},
        "phase_tags": ["domain_state"],
        "inputs": {"required": ["task_context"], "optional": []},
        "emits": [],
        "integrations": {},
        "context_budget": "medium",
        "version": "0.1.0",
        "bundle_schema_version": 2,
        "engine": {
            "kind": engine_kind,
            "contract": contract_name,
            "contract_version": contract_version,
        },
        "composition": {
            "group": domain,
            "mode": "composable",
            "requires": [],
            "conflicts": [],
        },
        "contracts": {"schemas": []},
        "flow_selection": {
            "fallback": "optional",
            "ambiguity": "error",
            "no_match": "inactive",
        },
    }
    if engine_kind == "state_machine":
        contract = {
            "version": "1.0.0",
            "initial_state": "NEW",
            "states": ["NEW", "COMPLETE"],
            "completion_states": ["COMPLETE"],
            "normal_path": ["NEW", "COMPLETE"],
            "transitions": [{
                "id": "complete-initial-scope",
                "from": "NEW",
                "to": "COMPLETE",
                "trigger": "complete",
                "required_evidence": ["plan"],
                "work_class": "assessment",
                "domain_effect": f"{domain}.complete",
                "progress_class": "TERMINAL",
                "path_class": "normal",
            }],
        }
    else:
        contract = {
            "version": "1.0.0",
            "steps": [{
                "id": "complete-initial-milestone",
                "label": f"Complete the first {display_name} milestone",
                "required_evidence": ["plan"],
                "work_class": "milestone",
                "domain_effect": f"{domain}.complete",
                "progress_class": "TERMINAL",
            }],
        }

    try:
        _write_yaml(bundle_root / "manifest.yaml", manifest)
        _write_yaml(bundle_root / contract_name, contract)
        (bundle_root / "guidance.md").write_text(
            f"# {display_name} guidance\n\n"
            "Keep this file for domain-specific model guidance. Routing and workflow "
            "authority come from the compiled manifest and workflow contract.\n",
            encoding="utf-8")
        (bundle_root / "README.md").write_text(
            f"# {display_name}\n\n"
            f"{purpose.strip()}\n\n"
            "Edit the manifest.yaml and workflow contract to define this bundle. "
            "Add local packet and evidence contracts under this directory when needed. "
            "Add flows in flows/<flow-name>/flow.md; each flow uses the bounded "
            "when predicate contract and the manifest flow_selection policy.\n",
            encoding="utf-8")
    except Exception:
        shutil.rmtree(bundle_root)
        raise
    return bundle_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("id", help="lowercase StateWork ID")
    parser.add_argument("--domain", required=True, help="lowercase domain identifier")
    parser.add_argument("--purpose", required=True, help="12-240 character purpose")
    parser.add_argument("--name", help="display name")
    parser.add_argument("--engine", choices=("state_machine", "milestone"),
                        default="state_machine")
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="CognitiveStateWork checkout root")
    args = parser.parse_args(argv)
    bundle = None
    try:
        bundle = scaffold(bundle_id=args.id, domain=args.domain, purpose=args.purpose,
                          engine_kind=args.engine, root=args.root, name=args.name)
        # Verify the starter contract before reporting success. The bundle is
        # a complete independent extension, so compilation also catches ID
        # collisions and shared-registry schema drift.
        RegistryCompiler(Path(args.root)).compile(write=False)
    except Exception as exc:
        if bundle is not None and bundle.is_dir() and not bundle.is_symlink():
            shutil.rmtree(bundle)
        print(f"new-statework: {exc}", file=sys.stderr)
        return 2
    print(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
