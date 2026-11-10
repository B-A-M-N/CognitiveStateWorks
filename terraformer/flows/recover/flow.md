---
flow: recover
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - recover
states:
  through: []
---
# Resolve partial, blocked or incompatible state

Re-observe effective versions and ownership, reverse/retry only authorized edges, test recovered behavior, and exit exception state with trusted evidence.

**Required recording:** current state, observed subject/revision, scope, evidence refs, outstanding unknowns, and legal next transition. Consult `../../transitions.yaml` for guards. This flow guides implementation; it does not issue host permissions or persist state directly.
