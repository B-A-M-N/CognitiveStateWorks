# Policy: Production Safety

Constraints that apply whenever the environment is production or
production-like.

## Standing rules

- **Observe before mutate.** No production change without current effective state. A model built five minutes ago may already be wrong.
- **Every production change is a hypothesis** until the running system verifies it. Plan the verification as part of the change.
- **Rollout gates must be able to stop the rollout.** Gates that only alert are advisory; critical gates stop automatically or operationally on failure: readiness stability, error rate, latency, capacity, dependency health, saturation, abnormal retries, data consistency.
- **Production equivalence honesty.** Evidence from test infrastructure that differs materially from production (topology, data volume, concurrency, latency, hardware, provider behavior, security policy, dependencies, traffic distribution) must state what it proves and what it does not.
- **Manual mutation is recorded mutation.** Manual production changes must record resulting state — an undocumented emergency fix is configuration drift waiting to be destroyed by the next reconciliation.
- **Do not optimize architecture during an active incident** unless necessary to restore safety.
- **Canary honesty.** A canary is evidence only with representative traffic, failure-sensitive metrics, meaningful sample size, and abort conditions. Trivial traffic for 30 seconds proves nothing.

## Readiness is per-envelope

`GREEN` production readiness applies only to a declared operating envelope
(workload, scale, failure assumptions). It never means universally
failure-proof, and the envelope is stated wherever the readiness class is.
