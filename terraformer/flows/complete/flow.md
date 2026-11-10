---
flow: complete
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - complete
states:
  through: []
---
# Publish verified scoped integration

Correlate independent evidence, exact revision and scope. Validate packet with stated limitations. Do not claim the entire product complete if only one slice was qualified.

**Required recording:** current state, observed subject/revision, scope, evidence refs, outstanding unknowns, and legal next transition. Consult `../../transitions.yaml` for guards. This flow guides implementation; it does not issue host permissions or persist state directly.
