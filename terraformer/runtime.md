# TerraFormer — Runtime Capsule

Architectural recomposition discipline. Validates real component
contracts, plans the smallest reversible connection slice, connects
through explicit interfaces without a central authority accumulator,
and qualifies end-to-end behavior. May conclude NO_COMPOSITION_NEEDED
or INCOMPATIBLE.

## State vocabulary

- UNASSESSED → CONTRACTS_VALIDATED
- CONTRACTS_VALIDATED → COMPOSITION_PLANNED
- CONTRACTS_VALIDATED → NO_COMPOSITION_NEEDED
- CONTRACTS_VALIDATED → INCOMPATIBLE
- COMPOSITION_PLANNED → CONNECTING
- CONNECTING → INTEGRATED
- CONNECTING → PARTIALLY_INTEGRATED
- INTEGRATED → QUALIFIED
- QUALIFIED → COMPLETE
- QUALIFIED → COMPOSITION_PLANNED
- INTEGRATED → COMPOSITION_PLANNED
- RECOVERY_REQUIRED → UNASSESSED
- BLOCKED → UNASSESSED
- INVALIDATED → UNASSESSED

Use only states and transitions declared in transitions.yaml. The runtime
resolver pins that contract; this capsule does not define a second state
machine.

## Hard gates

- Inventory effective contracts, versions, lifecycles, and ownership
  before planning; code existence is not availability.
- Consequential connection requires host/operator authorization on the
  current subject revision; stale approvals are rejected.
- QUALIFIED requires end-to-end, ownership-integrity, lifecycle-recovery,
  compatibility, and qualification evidence on the same subject revision.
  Unit tests alone never qualify integration.

## Exit produced

Emit `terraformer_integration_packet` under the canonical CSW handoff
envelope with `payload.architecture_boundary` conforming to
architecture-boundary/v1, including unresolved scope and rollback path.

## Completion

Done when the scoped integration is qualified and published, or a
terminal negative (NO_COMPOSITION_NEEDED, INCOMPATIBLE) is
evidence-backed. Partial integration stays explicit until resumed.
