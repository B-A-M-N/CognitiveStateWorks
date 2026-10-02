"""Filesystem and packaged resource helpers for the control plane."""
from __future__ import annotations

import json
from datetime import datetime
from importlib.resources import files as resource_files
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

import jsonschema
import yaml

_CODE_ROOT = Path(__file__).resolve().parent
_CHECKOUT_ROOT = Path(__file__).resolve().parents[1]
_PACKAGED_BUILTIN_ROOT = _CODE_ROOT / "builtin"
if (_CHECKOUT_ROOT / "registry.yaml").is_file():
    ROOT = _CHECKOUT_ROOT
elif (_PACKAGED_BUILTIN_ROOT / "registry.yaml").is_file():
    ROOT = _PACKAGED_BUILTIN_ROOT
else:
    ROOT = _CODE_ROOT
EVIDENCE_KIND_REGISTRY_PATH = ROOT / "schemas" / "evidence-kinds.yaml"


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def render_runtime_capsule(manifest: Mapping[str, Any], *, engine_kind: str,
                           contract_version: str, flows: Iterable[str],
                           guidance: str = "") -> str:
    """Render compact runtime guidance from machine-owned bundle metadata."""
    lines = [f"# {manifest.get('name') or manifest.get('id')} — StateWork",
             f"Domain: {manifest.get('domain') or 'unspecified'}",
             f"Purpose: {manifest.get('purpose') or 'unspecified'}",
             f"Workflow engine: {engine_kind} ({contract_version})"]
    flow_names = tuple(sorted(set(str(item) for item in flows if item)))
    if flow_names:
        lines.extend(["Available flows:", *[f"- {name}" for name in flow_names]])
    lines.extend([
        "Inspect current workflow progress and eligible steps through the host workflow authority.",
        "Use the selected flow as guidance; the workflow contract and host authority determine legal steps.",
    ])
    if guidance.strip():
        lines.extend(["", "## Domain guidance", "", guidance.strip()])
    return "\n".join(lines) + "\n"


def _aware_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be non-empty date-time text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp is not a valid date-time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


def _package_resource(relative: str):
    try:
        resource = resource_files("cognitive_statework").joinpath(relative)
        if resource.is_file():
            return resource
    except (ModuleNotFoundError, FileNotFoundError):
        pass
    return None


def _schema_resource(name: str):
    return _package_resource(f"schemas/{name}")


def _schema_text(name: str) -> str:
    resource = _schema_resource(name)
    if resource is not None:
        return resource.read_text(encoding="utf-8")
    return (ROOT / "schemas" / name).read_text(encoding="utf-8")


def load_evidence_kind_registry(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and validate the semantic evidence provenance registry."""
    if path is None and _package_resource("schemas/evidence-kinds.yaml") is not None:
        resource = _package_resource("schemas/evidence-kinds.yaml")
        data = yaml.safe_load(resource.read_text(encoding="utf-8"))
        schema = json.loads(_schema_text("evidence-kinds.schema.json"))
        jsonschema.validate(instance=data, schema=schema)
        return data
    registry_path = Path(path or EVIDENCE_KIND_REGISTRY_PATH)
    data = _load_yaml(registry_path)
    schema_path = registry_path.with_suffix(".schema.json")
    if schema_path.exists():
        jsonschema.validate(instance=data, schema=json.loads(schema_path.read_text(encoding="utf-8")))
    return data


def load_packet_registry(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the host's merged packet declarations and validate their envelope."""
    if path is None:
        resource = _package_resource("schemas/packet-registry.yaml")
        data = yaml.safe_load(resource.read_text(encoding="utf-8")) if resource else _load_yaml(
            ROOT / "schemas" / "packet-registry.yaml")
        schema = json.loads(_schema_text("packet-registry.schema.json"))
    else:
        path = Path(path)
        data = _load_yaml(path)
        schema_path = path.with_name("packet-registry.schema.json")
        schema = (json.loads(schema_path.read_text(encoding="utf-8"))
                  if schema_path.exists() else json.loads(_schema_text("packet-registry.schema.json")))
    jsonschema.validate(instance=data, schema=schema)
    return dict(data)


def _local_schema_registry() -> "jsonschema.validators.Registry":
    from referencing import Registry, Resource
    registry = Registry()
    resources = []
    try:
        resources = sorted(resource_files("cognitive_statework").joinpath("schemas").iterdir(),
                           key=lambda item: item.name)
    except (ModuleNotFoundError, FileNotFoundError):
        resources = sorted((ROOT / "schemas").glob("*.json"))
    for path in resources:
        if not path.name.endswith(".json"):
            continue
        schema = json.loads(path.read_text(encoding="utf-8"))
        uri = schema.get("$id")
        if uri:
            registry = registry.with_resource(uri, Resource.from_contents(schema))
    return registry
