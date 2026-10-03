"""Canonical StateWork composition rules shared by planning and authority."""
from __future__ import annotations

from typing import Any, Mapping


def composition_for(manifest: Mapping[str, Any]) -> dict[str, Any]:
    raw = manifest.get("composition") or {}
    if not isinstance(raw, Mapping):
        raise ValueError("StateWork composition must be an object")
    top_group = manifest.get("exclusive_group")
    declared_group = raw.get("group")
    if top_group and declared_group and top_group != declared_group:
        raise ValueError("exclusive_group and composition.group disagree")
    group = str(declared_group or top_group or "")
    mode = str(raw.get("mode") or ("exclusive" if top_group else "composable"))
    if mode not in {"exclusive", "composable"}:
        raise ValueError("StateWork composition mode is invalid")
    requires = raw.get("requires") or ()
    conflicts = raw.get("conflicts") or ()
    for name, values in (("requires", requires), ("conflicts", conflicts)):
        if (not isinstance(values, (tuple, list, set, frozenset))
                or any(not isinstance(item, str) or not item for item in values)
                or len(values) != len(set(values))):
            raise ValueError(f"StateWork composition {name} is malformed")
    return {"group": group, "mode": mode,
            "requires": frozenset(requires), "conflicts": frozenset(conflicts)}


def _depends_on(manifests: Mapping[str, Mapping[str, Any]],
                consumer_id: str, required_id: str) -> bool:
    pending = [consumer_id]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        manifest = manifests.get(current)
        if manifest is None:
            continue
        dependencies = composition_for(manifest)["requires"]
        if required_id in dependencies:
            return True
        pending.extend(item for item in dependencies if item in manifests)
    return False


def validate_selection(manifests: Mapping[str, Mapping[str, Any]],
                       selected_ids: set[str]) -> None:
    """Raise when a complete active/planned set violates canonical rules."""
    if not selected_ids.issubset(manifests):
        raise ValueError("StateWork selection contains an unavailable dependency")
    compositions = {statework_id: composition_for(manifests[statework_id])
                    for statework_id in selected_ids}
    for statework_id, composition in compositions.items():
        missing = composition["requires"] - selected_ids
        if missing:
            raise ValueError(
                f"StateWork {statework_id!r} is missing requirements {sorted(missing)}")
        conflicts = set(composition["conflicts"] & selected_ids)
        conflicts.update(
            other_id for other_id, other in compositions.items()
            if statework_id in other["conflicts"])
        if conflicts:
            raise ValueError(
                f"StateWork {statework_id!r} conflicts with {sorted(conflicts)}")

    ids = sorted(selected_ids)
    for index, left in enumerate(ids):
        left_composition = compositions[left]
        if not left_composition["group"]:
            continue
        for right in ids[index + 1:]:
            right_composition = compositions[right]
            if left_composition["group"] != right_composition["group"]:
                continue
            if (left_composition["mode"] != "exclusive"
                    and right_composition["mode"] != "exclusive"):
                continue
            if not _depends_on(manifests, left, right) and not _depends_on(
                    manifests, right, left):
                raise ValueError(
                    f"exclusive StateWork group {left_composition['group']!r} "
                    f"contains independent members {left!r} and {right!r}")


__all__ = ["composition_for", "validate_selection"]
