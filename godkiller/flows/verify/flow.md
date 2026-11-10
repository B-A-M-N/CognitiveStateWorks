---
flow: verify
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - verify
states:
  through: []
---
# Independently verify separation

Run baseline behavior oracle, ownership/single-writer proof, dependency/cycle checks, error and concurrency paths, and rollback check. Reject cosmetic file-splitting and stale evidence.

**Required recording:** current state, observed subject/revision, scope, evidence refs, outstanding unknowns, and legal next transition. Consult `../../transitions.yaml` for guards. This flow guides implementation; it does not issue host permissions or persist state directly.
