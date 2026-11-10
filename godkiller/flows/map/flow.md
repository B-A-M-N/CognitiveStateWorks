---
flow: map
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - map
states:
  through: []
---
# Map observed structure

Inventory components, decisions, side effects, public contracts, real dependencies and mutable resources. Record confirmed vs inferred state. Produce an ownership/resource graph and missing observations.

**Required recording:** current state, observed subject/revision, scope, evidence refs, outstanding unknowns, and legal next transition. Consult `../../transitions.yaml` for guards. This flow guides implementation; it does not issue host permissions or persist state directly.
