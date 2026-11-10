---
flow: diagnose
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - diagnose
states:
  through: []
---
# Decide whether decomposition is justified

Apply criteria in references/diagnosis.md, including legitimate centralized authorities. Show mechanism and alternatives. An evidence-backed NO_DECOMPOSITION_NEEDED is valid.

**Required recording:** current state, observed subject/revision, scope, evidence refs, outstanding unknowns, and legal next transition. Consult `../../transitions.yaml` for guards. This flow guides implementation; it does not issue host permissions or persist state directly.
