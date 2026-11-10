---
flow: extract
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - extract
states:
  through: []
---
# Make authorized incremental extraction

Capture exact revision and approval. Introduce seam, transfer authority once, route consumers, verify one slice, and stop on contradictory observation. Never mutate before guards.

**Required recording:** current state, observed subject/revision, scope, evidence refs, outstanding unknowns, and legal next transition. Consult `../../transitions.yaml` for guards. This flow guides implementation; it does not issue host permissions or persist state directly.
