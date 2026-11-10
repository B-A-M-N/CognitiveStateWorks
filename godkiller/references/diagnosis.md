# Diagnosing excessive centralization

## Inventory the real surface

For each candidate collect responsibility statements (verbs with independent outcomes), public consumers, commands/queries, decisions/policies, mutable resources, side effects, failure and cancellation paths, startup/shutdown ownership, observability, and runtime call graphs. Include undocumented direct access from other components.

## Evidence-based discriminators

1. **Reasons to change:** unrelated product decisions force edits in the same owner. Correlate change history or independently identifiable policy domains.
2. **Authority coupling:** one object controls multiple unrelated resource transitions or all policy decisions when those resources have natural independent owners.
3. **State leakage:** callers must know internal storage or mutation ordering; consumers reach across boundaries.
4. **Dependency concentration:** one hub imports every subsystem and is imported by them; bypasses contracts; controls retry/queue/cancellation unrelated to its domain.
5. **Test/operational coupling:** a change in one responsibility forces irrelevant fixtures, full-system lifecycle, or broad permissions.
6. **Cycles:** bidirectional reach-through, cyclic initialization, event callbacks effectively recreating central authority.

**Counterexamples:** intentionally centralized transaction coordinator, admission controller, security policy decision point, single-threaded event loop, actor mailbox, or canonical state owner can be correct when responsibility is coherent, authority explicit, and consumers interact through a stable contract. Preserve those semantics. Count concerns and invariants, not lines or methods.

## Decision

Return `DIAGNOSED` only with observed concentration, causal mechanism, impacted invariants, alternatives, and evidence. Return `NO_DECOMPOSITION_NEEDED` when owner coherence outweighs extra abstraction and there is no proven architectural harm. Mark uncertainty explicitly; do not force a decomposition verdict from a metric threshold.
