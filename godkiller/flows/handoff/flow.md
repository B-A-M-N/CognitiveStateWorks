---
flow: handoff
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - handoff
states:
  through: []
---
# Publish verified bounded outcome

Validate architecture facts, packet envelope, fresh fingerprint and provenance. Publish evidence-backed boundary with residuals and scope. A handoff is available to any consumer; do not invoke a peer skill.

**Required recording:** current state, observed subject/revision, scope, evidence refs, outstanding unknowns, and legal next transition. Consult `../../transitions.yaml` for guards. This flow guides implementation; it does not issue host permissions or persist state directly.
