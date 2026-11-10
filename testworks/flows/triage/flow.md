---
flow: triage
required_specialists: []
optional_specialists: []
fallback: true
---
# Triage flow

**Purpose.** Inventory the change, test inventory, prior regressions, risk and confidence in existing results.

## Steps
1. Record observed revision, dirty-tree state and test environment. Unknown values are explicit.
2. Map affected behaviors, contracts, state transitions and critical invariants; classify impact independently of test count.
3. Inventory existing tests and their fault-detection purposes, costs, receipt quality and recency.
4. Identify gaps and downstream qualification requirements; hand off to strategy and selection rather than generating automatically.

## Required outputs
- inventory evidence with revision bindings
- protected-invariant inventory
- risk classification
- unknowns and next decision

## Stop / refuse
- No trustworthy subject identity
- Scope of observed code cannot be established

## Boundary
When repository observation or ownership is absent, request a Gitter truth packet through composition.
