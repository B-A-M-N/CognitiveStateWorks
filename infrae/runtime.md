# Infrae — Runtime Capsule

Infrastructure state discipline. Governs topology, availability, capacity,
trust boundaries, deployment, incident response, observability. Requires
infrastructure truth before mutation; treats rollback, blast radius, and
observability as first-class.

## State vocabulary
- UNKNOWN → OBSERVED → STABLE
- STABLE → DEGRADED / INCIDENT on availability, capacity, or topology change
- Any system evidence (reachability, 200 OK, green dashboard, backup
  existence) proves only itself, never health.

## Gates
- Establish `infrastructure_truth_packet` before mutation; accept a prior
  valid truth packet when resuming (never require it).
- Mutations carry a rollback plan and a defined blast radius.
- After mutation emit `infrastructure_evidence_packet` with result evidence.

## Completion
Done when infrastructure state is observed, the mutation is risk-gated and
executed with rollback available, and evidence is emitted.
