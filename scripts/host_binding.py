"""Resolve scope-safe CSW workflow bindings for independent runtime hosts.

This module does not depend on CFW or DigitalPsychology. It derives bindings
from CSW's compiled registry and asks WorkflowAuthority which registered
workflows are compatible with the current selection.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

if __package__:
    from .control_plane import load_compiled_registry
else:
    from control_plane import load_compiled_registry


_SCOPE_FIELDS = (
    "namespace_id", "application_id", "application_instance_id",
    "workflow_id", "subject_ref",
)
_IDENTITY_FIELDS = frozenset((*_SCOPE_FIELDS, "statework_id", "contract_version"))
_TASK_CONTEXT_FIELDS = frozenset({
    "candidate_statework_ids", "domains", "behavior_tags",
})


@dataclass(frozen=True)
class CSWWorkflowBinding:
    """Immutable identity and contract pin accepted by neutral host adapters."""

    identity: Mapping[str, str]
    contract_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.identity, Mapping) or set(self.identity) != _IDENTITY_FIELDS:
            raise ValueError("CSW workflow binding identity fields are invalid")
        identity = dict(self.identity)
        if any(not isinstance(value, str) or not value.strip() or len(value) > 256
               for value in identity.values()):
            raise ValueError("CSW workflow binding identity values are invalid")
        digest = self.contract_hash
        if (not isinstance(digest, str) or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)):
            raise ValueError("CSW workflow binding contract hash must be SHA-256")
        object.__setattr__(self, "identity", MappingProxyType(identity))


def _scope_from_runtime_identity(runtime_identity: Any) -> dict[str, str]:
    scope_method = getattr(runtime_identity, "csw_scope", None)
    if callable(scope_method):
        raw = scope_method()
    elif isinstance(runtime_identity, Mapping):
        raw = runtime_identity
    else:
        raw = {name: getattr(runtime_identity, name, None) for name in _SCOPE_FIELDS}
    if not isinstance(raw, Mapping):
        raise TypeError("runtime identity must expose its CSW workflow scope")
    scope = {name: raw.get(name) for name in _SCOPE_FIELDS}
    if any(not isinstance(value, str) or not value.strip() or len(value) > 256
           for value in scope.values()):
        raise ValueError("runtime identity has an invalid CSW workflow scope")
    return {name: str(scope[name]) for name in _SCOPE_FIELDS}


def _bounded_ids(value: Any, *, field: str, limit: int) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple, set, frozenset)) or len(value) > limit:
        raise ValueError(f"task context {field} is malformed or exceeds its bound")
    items = tuple(value)
    if (any(not isinstance(item, str) or not item.strip() or len(item) > 128
            for item in items) or len(items) != len(set(items))):
        raise ValueError(f"task context {field} must contain unique bounded IDs")
    return items


def _task_candidates(entries: Mapping[str, Mapping[str, Any]],
                     task_context: Mapping[str, Any]) -> tuple[str, ...]:
    if not isinstance(task_context, Mapping) or set(task_context) - _TASK_CONTEXT_FIELDS:
        raise ValueError("task context contains unsupported workflow selection fields")
    requested = _bounded_ids(task_context.get("candidate_statework_ids"),
                             field="candidate_statework_ids", limit=32)
    domains = _bounded_ids(task_context.get("domains"), field="domains", limit=16)
    tags = _bounded_ids(task_context.get("behavior_tags"), field="behavior_tags", limit=32)
    candidates = set(requested) if requested else set(entries)
    unknown = candidates - set(entries)
    if unknown:
        raise ValueError(f"task context names unregistered StateWorks: {sorted(unknown)}")
    if domains:
        candidates = {statework_id for statework_id in candidates
                      if str((entries[statework_id].get("manifest") or {}).get("domain") or "")
                      in domains}
    if tags:
        candidates = {statework_id for statework_id in candidates
                      if set((entries[statework_id].get("manifest") or {}).get(
                          "behavior_tags") or ()).intersection(tags)}
    return tuple(sorted(candidates))


def resolve_bindings(authority: Any, runtime_identity: Any,
                     task_context: Mapping[str, Any] | None = None
                     ) -> tuple[CSWWorkflowBinding, ...]:
    """Return registered, scope-valid, composition-compatible workflow pins.

    ``authority`` is a CSW ``WorkflowAuthority``. ``task_context`` may narrow
    candidates with registered IDs, domains, or behavioral tags. Already
    active workflows in the exact runtime scope are always included so a host
    can continue observing them even when a later task filter is narrower.
    """
    if task_context is None:
        task_context = {}
    scope = _scope_from_runtime_identity(runtime_identity)
    root = getattr(authority, "root", None)
    snapshot_fn = getattr(authority, "behavioral_snapshot", None)
    contract_fn = getattr(authority, "workflow_contract_identity", None)
    if root is None or not callable(snapshot_fn) or not callable(contract_fn):
        raise TypeError("authority must expose the CSW WorkflowAuthority contract")

    compiled = load_compiled_registry(root)
    entries = {str(row.get("id")): row
               for row in compiled.get("stateworks") or ()
               if isinstance(row, Mapping) and isinstance(row.get("id"), str)}
    candidates = _task_candidates(entries, task_context)
    snapshot = snapshot_fn(workflow_scope=scope,
                           candidate_statework_ids=candidates)
    active_rows = snapshot.get("active_workflows") or ()
    eligible_rows = snapshot.get("eligible_stateworks") or ()
    if len(active_rows) > 16 or len(eligible_rows) > 32:
        raise ValueError("CSW workflow snapshot exceeds the host binding bound")

    active: dict[str, Mapping[str, Any]] = {}
    for row in active_rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("identity"), Mapping):
            raise ValueError("CSW active workflow identity is malformed")
        identity = dict(row["identity"])
        statework_id = identity.get("statework_id")
        if (set(identity) != _IDENTITY_FIELDS or statework_id not in entries
                or any(identity.get(name) != scope[name] for name in _SCOPE_FIELDS)):
            raise PermissionError("CSW active workflow escapes the runtime scope")
        if statework_id in active:
            raise ValueError("CSW active workflow snapshot has duplicate IDs")
        active[str(statework_id)] = row

    eligible: set[str] = set()
    for row in eligible_rows:
        if not isinstance(row, Mapping):
            raise ValueError("CSW eligible workflow row is malformed")
        statework_id = row.get("statework_id")
        if not isinstance(statework_id, str) or statework_id not in entries:
            raise PermissionError("CSW returned an unregistered eligible workflow")
        eligible.add(statework_id)

    bindings: list[CSWWorkflowBinding] = []
    for statework_id in sorted(set(active) | eligible):
        active_row = active.get(statework_id)
        pinned_hash = (active_row.get("contract_hash") if active_row is not None else None)
        contract = contract_fn(statework_id, contract_hash=pinned_hash)
        contract_version = contract.get("contract_version")
        contract_hash = contract.get("contract_hash")
        if not isinstance(contract_version, str) or not contract_version:
            raise ValueError("CSW workflow contract version is missing")
        identity = {**scope, "statework_id": statework_id,
                    "contract_version": contract_version}
        if active_row is not None and dict(active_row["identity"]) != identity:
            raise PermissionError("CSW active workflow identity differs from its contract pin")
        bindings.append(CSWWorkflowBinding(identity=identity,
                                           contract_hash=str(contract_hash or "")))
    return tuple(bindings)


__all__ = ["CSWWorkflowBinding", "resolve_bindings"]
