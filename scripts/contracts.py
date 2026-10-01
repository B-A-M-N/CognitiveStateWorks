"""Shared parsing and validation for bundle-local StateWork contracts."""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Mapping

import jsonschema
import yaml
from referencing import Registry, Resource

try:
    from .bundles import BundleFiles
    from .control_plane import TransitionError
    from .flow_selectors import FlowSelector
except ImportError:
    from bundles import BundleFiles
    from control_plane import TransitionError
    from flow_selectors import FlowSelector


def load_fragment(bundle_root: Path, relative: str | None, *, fragment: str) -> dict[str, Any]:
    if not relative:
        return {}
    path = BundleFiles.relative_file(bundle_root, relative)
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, Mapping) or not isinstance(value.get(fragment), Mapping):
        raise TransitionError(f"{fragment} contract fragment must be a mapping")
    return dict(value[fragment])


def validate_flow_file(flow_path: Path, *, flow_schema: Mapping[str, Any],
                       engine_kind: str) -> dict[str, Any]:
    pieces = flow_path.read_text(encoding="utf-8").split("---", 2)
    if len(pieces) != 3 or pieces[0].strip():
        raise TransitionError(
            f"StateWork flow {flow_path.parent.name!r} lacks frontmatter")
    try:
        flow_meta = yaml.safe_load(pieces[1]) or {}
        jsonschema.validate(instance=flow_meta, schema=flow_schema)
        if not isinstance(flow_meta, Mapping):
            raise TransitionError("flow frontmatter must be a mapping")
        if flow_meta.get("flow") != flow_path.parent.name:
            raise TransitionError(
                f"StateWork flow {flow_path.parent.name!r} differs from its directory")
        if flow_meta.get("states") and engine_kind != "state_machine":
            raise TransitionError(
                f"non-state-machine flow {flow_path.parent.name!r} cannot declare states")
        if "when" in flow_meta:
            FlowSelector.validate_predicate(flow_meta["when"])
    except (ValueError, jsonschema.ValidationError, yaml.YAMLError) as exc:
        raise TransitionError(
            f"StateWork flow {flow_path.parent.name!r} is invalid: {exc}") from exc
    return dict(flow_meta)


def validate_packet_schema(bundle_root: Path, declaration: Mapping[str, Any]
                           ) -> tuple[Path, dict[str, Any]]:
    schema_relative = str(declaration.get("schema") or "")
    schema_path = BundleFiles.relative_file(bundle_root, schema_relative)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema_path, schema


def validate_packet(packet: Mapping[str, Any], schema: Mapping[str, Any], *,
                    reference_schemas: Iterable[Mapping[str, Any]] = ()) -> None:
    """Validate a packet without permitting remote reference resolution."""
    jsonschema.Draft202012Validator.check_schema(schema)
    registry = Registry()
    documents = [*reference_schemas, schema]
    for document in documents:
        uri = document.get("$id")
        if uri:
            registry = registry.with_resource(uri, Resource.from_contents(document))
    validator = jsonschema.Draft202012Validator(
        schema, registry=registry, format_checker=jsonschema.FormatChecker())
    validator.validate(dict(packet))


__all__ = ["load_fragment", "validate_flow_file", "validate_packet_schema",
           "validate_packet"]
