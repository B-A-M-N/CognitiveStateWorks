---
flow: connect
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - connect
states:
  through: []
---
# Connect with explicit interfaces

With host authorization, wire the smallest slice and exercise edge contracts. If only part of the path works, report PARTIALLY_INTEGRATED and preserve recovery state.

**Required recording:** current state, observed subject/revision, scope, evidence refs, outstanding unknowns, and legal next transition. Consult `../../transitions.yaml` for guards. This flow guides implementation; it does not issue host permissions or persist state directly.
