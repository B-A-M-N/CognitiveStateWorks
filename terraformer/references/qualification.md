# Qualification: prove a coherent integrated system

For each required user/system journey trace the **entire path** through actual connected components, including identity, input, transitions, output, observable result, and correlated errors. Use test doubles only for explicitly scoped contract checks; they cannot replace the integrated environment for a system-wide claim.

Evidence matrix:

| Claim | Required observation |
|---|---|
| Existence/compatibility | Each actual endpoint/interface and effective version discovered and exercised |
| Correct result | External stimulus → boundary interactions → expected observable outcome |
| Ownership | Sole writer or verified shared-authority protocol across real participants |
| Lifecycle | Ordered startup, readiness, cancellation, teardown, failure and recovery for the relevant system |
| Reliability | Retries, timeouts, idempotency, backpressure and concurrency as appropriate |
| Compatibility | Existing consumers remain functional, or change explicitly authorized and documented |
| Security | Authentication, permission and trust propagation across boundaries where present |
| Recovery | Partial failure or restart restores invariants, not just process liveness |

**Adversarial failures:** individually passing components cannot exchange messages; two components both assert ownership of one state; startup deadlock; cancellation not propagated; retry duplicates mutation; stale packet passes; integration hub becomes universal authority; partial path claimed COMPLETE. Every one must be detected and block full qualification.
