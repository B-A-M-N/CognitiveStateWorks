# Gitter — Runtime Capsule

Repository-state observation and truth establishment. Owns OBSERVE, MODEL,
CLASSIFY RISK, REPORT. Runs before any Git mutation.

## State vocabulary
- UNKNOWN → OBSERVED (observation of HEAD, branch, worktree, ownership)
- OBSERVED → STALE (any HEAD change, working-tree mutation, branch
  force-push, user/operator contradiction, concurrent worker touch)

Invariant: a user report like "another agent touched this" or "this looks
mixed together" is a state-invalidating observation requiring re-inspection,
never a casual remark.

## Exit produced
Emit `repository_truth_packet` (nested payload: repository / change /
assessment / freshness — see schemas/repository-truth-packet.schema.json)
before any nontrivial recommendation; freshness fingerprints make the packet
self-validating.

## Completion
Done when repository state is observed, ownership established, risk
classified, and a handoff recommendation is explicit. Then hand off to
getter for MUTATE.
