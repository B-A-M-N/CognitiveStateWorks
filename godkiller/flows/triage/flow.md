---
flow: triage
required_specialists: []
optional_specialists: []
fallback: true
states:
  through:
  - UNASSESSED
---
# UNASSESSED/MAPPED discovery

When context is incomplete, discover the actual subject, intended scope, authority, baseline, evidence sources, and what user-facing behavior must not change. Route to a diagnostic plan; do not presume God Object.

**Required recording:** current state, observed subject/revision, scope, evidence refs, outstanding unknowns, and legal next transition. Consult `../../transitions.yaml` for guards. This flow guides implementation; it does not issue host permissions or persist state directly.
