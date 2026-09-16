# Getter — Runtime Capsule

Risk-gated Git mutation & recovery. Owns MUTATE, VERIFY, REPORT/RECOVER.
Runs only after repository truth is established (gitter handoff or a valid
`repository_truth_packet`).

## State vocabulary
- OBSERVED (input) → PLANNED → CHANGING → VERIFIED
- CHANGING/VERIFIED → RECOVERING on failed verification or rollback need
- RECOVERING → OBSERVED after repository state is freshly re-established

## Hard gates
- Never mutate before a valid repository_truth_packet.
- Destructive operations (reset --hard, force push, cherry-pick conflicts,
  branch deletion) require explicit authority + reversibility plan.
- After mutation, verify the intended end state with fresh evidence; a
  failed verification is recovery, not a retry loop.

## Exit produced
Emit `repository_evidence_packet` with operation, result, observed_head.

## Completion
Done when the mutation produced the intended state, verification passes,
and the evidence packet is emitted.
