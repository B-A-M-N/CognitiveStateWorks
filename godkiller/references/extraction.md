# Controlled extraction playbook

## Before each authorized change

(1) Record exact observed revision and protected user-visible behavior. (2) Enumerate ownership transfers. (3) Build characterization oracles covering normal/error/concurrent/lifecycle paths in scope. (4) Specify new contract/version. (5) Confirm operator/host authority, blast radius, and rollback. (6) Define a single slice boundary and exit criteria.

## Execution order (adapt as necessary)

1. Introduce narrow seam or adapter **without** changing behavior. Validate forwarding and input/output equivalence.
2. Move logic that has no mutable authority first when it materially reduces risk; keep semantics and instrumentation.
3. Transfer authoritative state and transitions exactly once. Avoid dual-writers; if coexistence required, describe explicit single-writer cutover or coordinated protocol.
4. Rewire only scoped consumers to the new contract. Enforce no reach-through; retire old direct access in that slice.
5. Exercise baseline/contract/concurrency checks against the new revision. If unexpected difference, stop and recover. Do not pile more extraction on a failed gate.
6. Compare dependency graph, owner map, permission footprint, and operational coupling against baseline. Verify improvement beyond file count.
7. Publish traceable evidence and snapshot; repeat another slice through `VERIFIED → PARTITIONED` only after previous slice qualifies.

## Rollback / recovery

Use a predeclared reversible action with data compatibility. Where schema or externally persisted state changes, 'revert code' alone may not restore correctness. Preserve durable state validity and evidence; re-observe recovered behavior before resuming.
