# Policy: Destructive Change

Governs destructive and hard-to-reverse infrastructure operations.

## Classification reminder

Destructive operations are CRITICAL risk class by default: deleting
production state, replacing trust roots, destructive schema/data migration,
storage ownership rewrite, authentication authority change. CRITICAL does not
pass the Mutation Gate — isolate or recover first.

## Requirements before any destructive operation

1. **Recovery anchor exists.** Snapshot, backup, out-of-band access, known-good configuration — and the anchor itself must survive the operation (a backup on the volume being destroyed is not an anchor).
2. **Restore evidence, not restore hope.** For destructive data operations: the restore path has been tested, or the operation does not run.
3. **Rollback-or-forward plan.** Either a real rollback plan (mechanism, dependencies, verification, failure-of-rollback) or an explicit forward-recovery plan for the irreversible case.
4. **Blast radius re-checked at the worst transition moment**, not just the endpoint.
5. **Verification defined before execution** — what observation will distinguish success from quiet corruption.

## Controlled failure testing

Failure injection is deliberate destructive work: scope, expected behavior,
abort condition, monitoring, recovery, affected users, ownership established
first. Uncontrolled destructive experiments on critical infrastructure are
never acceptable. After aborting an experiment, verify the abort itself
restored the pre-experiment state.

## Decommission is destruction with paperwork

Removing infrastructure follows the Decommission flow's gate. "It's just
cleanup" is how unknown consumers get destroyed. A decommission ends in
BLOCKED when consumers are unknown — that is a successful gate outcome, not a
failed decommission.
