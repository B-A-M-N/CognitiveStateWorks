# GodKiller — Runtime Capsule

Architectural decomposition discipline. Diagnoses responsibility
concentration, designs legitimate ownership boundaries, extracts one
reversible slice at a time, and verifies separation with behavior,
ownership, and regression evidence. May conclude NO_DECOMPOSITION_NEEDED.

## State vocabulary

- UNASSESSED → MAPPED
- MAPPED → DIAGNOSED
- MAPPED → NO_DECOMPOSITION_NEEDED
- DIAGNOSED → NO_DECOMPOSITION_NEEDED
- DIAGNOSED → PARTITIONED
- PARTITIONED → EXTRACTING
- EXTRACTING → VERIFIED
- VERIFIED → HANDOFF_READY
- VERIFIED → PARTITIONED
- EXTRACTING → PARTITIONED
- RECOVERY_REQUIRED → MAPPED
- BLOCKED → MAPPED
- INVALIDATED → MAPPED

Use only states and transitions declared in transitions.yaml. The runtime
resolver pins that contract; this capsule does not define a second state
machine.

## Hard gates

- Establish inventory and behavioral baselines before diagnosing; size
  alone never justifies decomposition.
- Consequential extraction requires host/operator authorization on the
  current subject revision; stale approvals are rejected.
- VERIFIED requires change result, boundary independence, and current
  regression evidence on the same subject revision.

## Exit produced

Emit `godkiller_boundary_packet` under the canonical CSW handoff envelope
with `payload.architecture_boundary` conforming to architecture-boundary/v1,
including residuals and scope limits.

## Completion

Done when the boundary is verified or NO_DECOMPOSITION_NEEDED is
evidence-backed, and the packet is published. Partial extraction stays in
EXTRACTING until verified.
