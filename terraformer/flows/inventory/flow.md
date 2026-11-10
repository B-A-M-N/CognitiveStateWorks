---
flow: inventory
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - inventory
states:
  through: []
---
# Inventory real components

Inspect effective contracts, versions, lifecycles, external consumers and ownership. Record missing components and runtime capabilities; do not confuse code existence with availability.

**Required recording:** current state, observed subject/revision, scope, evidence refs, outstanding unknowns, and legal next transition. Consult `../../transitions.yaml` for guards. This flow guides implementation; it does not issue host permissions or persist state directly.
