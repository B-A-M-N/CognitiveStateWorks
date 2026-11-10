---
flow: reconcile
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - reconcile
states:
  through: []
---
# Validate contract compatibility

Compare producer/consumer assumptions, version/error/cancel/ordering/consistency and trust semantics. Record incompatibilities; INCOMPATIBLE is a valid outcome.

**Required recording:** current state, observed subject/revision, scope, evidence refs, outstanding unknowns, and legal next transition. Consult `../../transitions.yaml` for guards. This flow guides implementation; it does not issue host permissions or persist state directly.
