---
flow: partition
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - partition
states:
  through: []
---
# Design coherent boundaries

Specify responsibility and state authority for every proposed component, typed interface obligations, dependency direction, migration slices and rollback. Run fake-decomposition detector.

**Required recording:** current state, observed subject/revision, scope, evidence refs, outstanding unknowns, and legal next transition. Consult `../../transitions.yaml` for guards. This flow guides implementation; it does not issue host permissions or persist state directly.
