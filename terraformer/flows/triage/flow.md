---
flow: triage
required_specialists: []
optional_specialists: []
fallback: true
states:
  through:
  - UNASSESSED
---
# UNASSESSED discovery

Find actual components, contracts, subject revision and user journeys. Accept arbitrary sources, verify before trusting them, and avoid assuming a prior decomposition.

**Required recording:** current state, observed subject/revision, scope, evidence refs, outstanding unknowns, and legal next transition. Consult `../../transitions.yaml` for guards. This flow guides implementation; it does not issue host permissions or persist state directly.
