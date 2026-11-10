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
# Recover and invalidate safely

Stop changes; inspect current revision/effective state. Use existing rollback or forward-repair route with authorization, verify restored invariants, and re-enter at MAPPED or BLOCKED.

**Required recording:** current state, observed subject/revision, scope, evidence refs, outstanding unknowns, and legal next transition. Consult `../../transitions.yaml` for guards. This flow guides implementation; it does not issue host permissions or persist state directly.
