---
flow: qualify
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - qualify
states:
  through: []
---
# Run end-to-end integration qualification

Exercise external entry to outcome, error/cancellation/retry paths, state authority and operational lifecycle. Isolated unit tests cannot satisfy QUALIFIED.

**Required recording:** current state, observed subject/revision, scope, evidence refs, outstanding unknowns, and legal next transition. Consult `../../transitions.yaml` for guards. This flow guides implementation; it does not issue host permissions or persist state directly.
