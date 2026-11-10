"""Host-validated architectural assessment for GodKiller decomposition claims.

A file split, lower line count, or passing unit tests alone must not qualify
decomposition. This module gives the trusted host a bounded, deterministic
check over a structured decomposition claim before it approves
``EXTRACTING -> VERIFIED``:

- every responsibility has exactly one owning component;
- dependency direction is acyclic;
- no shared mutable state crosses a component boundary without an explicit
  coordination contract (rejects cosmetic splits and hidden coupling);
- claimed interfaces are preserved and backed by regression evidence refs;
- a single component owning everything is NO_DECOMPOSITION_NEEDED, not a
  failure (doing nothing is the correct outcome for a legitimate
  centralized authority);
- the claim is bound to an exact subject revision (stale claims rejected).

Jev may recommend which boundary to investigate. It must not certify that
an extracted component is independent -- only this host-side assessment,
over host-observed evidence, gates the transition.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Component:
    id: str
    responsibilities: tuple[str, ...] = ()
    owns_state: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()


@dataclass(frozen=True)
class Dependency:
    source: str
    target: str
    kind: str = "call"


@dataclass(frozen=True)
class SharedMutableState:
    name: str
    writers: tuple[str, ...] = ()
    readers: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecompositionClaim:
    subject_ref: str
    subject_revision: int
    components: tuple[Component, ...] = ()
    dependencies: tuple[Dependency, ...] = ()
    shared_mutable: tuple[SharedMutableState, ...] = ()
    coordination_contracts: tuple[str, ...] = ()
    interface_preserved: bool = False
    regression_evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Assessment:
    verdict: str  # APPROVED | NO_DECOMPOSITION_NEEDED | REJECTED
    reasons: tuple[str, ...] = ()

    @property
    def approved(self) -> bool:
        return self.verdict == "APPROVED"


def assess_decomposition(claim: DecompositionClaim,
                         *, current_revision: int) -> Assessment:
    """Assess a decomposition claim against the current subject revision."""
    reasons: list[str] = []
    if claim.subject_revision != current_revision:
        return Assessment("REJECTED", (
            f"stale claim revision {claim.subject_revision} "
            f"(current {current_revision}); re-observe before approval",))
    if not claim.components:
        return Assessment("REJECTED", ("no components declared",))

    by_id = {component.id: component for component in claim.components}
    unknown = [dep for dep in claim.dependencies
               if dep.source not in by_id or dep.target not in by_id]
    if unknown:
        reasons.append("dependencies reference undeclared components: " + ", ".join(
            sorted({dep.source for dep in unknown} |
                   {dep.target for dep in unknown})))

    ownership: dict[str, list[str]] = {}
    for component in claim.components:
        for responsibility in component.responsibilities:
            ownership.setdefault(responsibility, []).append(component.id)
    for responsibility, owners in sorted(ownership.items()):
        if len(owners) != 1:
            reasons.append(
                f"responsibility {responsibility!r} has {len(owners)} owners "
                f"({', '.join(owners)}); exactly one owner required")

    order: dict[str, int] = {}
    stack = sorted(by_id)
    visit_state: dict[str, int] = {}

    def visit(node: str, path: tuple[str, ...]) -> bool:
        visit_state[node] = 1
        for dep in claim.dependencies:
            if dep.source != node or dep.target not in by_id:
                continue
            if visit_state.get(dep.target) == 1:
                cycle = " -> ".join(path + (node, dep.target))
                reasons.append(f"circular dependency: {cycle}")
                return False
            if visit_state.get(dep.target) != 2:
                if not visit(dep.target, path + (node,)):
                    return False
        visit_state[node] = 2
        order[node] = len(order)
        return True

    for root in stack:
        if visit_state.get(root) is None:
            visit(root, ())

    contracted = set(claim.coordination_contracts)
    for shared in claim.shared_mutable:
        writers = [writer for writer in shared.writers if writer in by_id]
        if len(set(writers)) > 1 and shared.name not in contracted:
            reasons.append(
                f"shared mutable state {shared.name!r} has multiple writers "
                f"({', '.join(sorted(set(writers)))}) without an explicit "
                "coordination contract; cosmetic splits do not qualify")
        readers_outside = [reader for reader in shared.readers
                           if reader in by_id
                           and reader not in writers
                           and shared.name not in contracted]
        if writers and readers_outside and shared.name not in contracted:
            reasons.append(
                f"shared mutable state {shared.name!r} is written by "
                f"{', '.join(sorted(set(writers)))} but read across the "
                "boundary without a coordination contract")

    if not claim.interface_preserved:
        reasons.append("interface preservation not demonstrated")
    if not claim.regression_evidence_refs:
        reasons.append("no behavioral regression evidence refs supplied")

    if reasons:
        return Assessment("REJECTED", tuple(reasons))

    if len(claim.components) == 1 and not claim.dependencies:
        only = claim.components[0]
        return Assessment("NO_DECOMPOSITION_NEEDED", (
            f"{only.id} retains single ownership of "
            f"{len(only.responsibilities)} responsibilities; size alone "
            "is not evidence to split",))

    provided = {name for component in claim.components for name in component.provides}
    required = {name for component in claim.components for name in component.requires}
    unmet = sorted(required - provided)
    if unmet:
        return Assessment("REJECTED", (
            "required interfaces without a provider: " + ", ".join(unmet),))
    return Assessment("APPROVED", ("single ownership holds; dependencies acyclic; "
                                   "no uncoordinated shared mutable state; "
                                   "interfaces preserved with regression evidence",))


__all__ = ["Assessment", "Component", "DecompositionClaim", "Dependency",
           "SharedMutableState", "assess_decomposition"]
