# Verification matrix: decomposition

A successful build is construction evidence. For each slice collect independently observed outcomes:

| Claim | Minimum relevant proof |
|---|---|
| External behavior unchanged | Characterization/contract tests on pre/post revisions with meaningful assertions |
| State owner moved | Runtime/structural inspection proving sole writer or documented coordination |
| Responsibility isolated | Unit/contract tests exercising component without original giant context where feasible |
| Coupling improved | Dependency-edge diff plus removal of reach-through/cycles/unrelated mutation authority |
| Errors/cancel/timeouts preserved | End-to-end failure-path behavior in scoped boundary |
| Concurrency safe | Interleaving/race/state-transition observations at risk points |
| Rollback viable | Tested or reasoned from actual state and compatibility constraints; high-risk paths require an exercise |
| Compatibility preserved | Public callers, serialization, config, events, and operational interfaces checked |

**Adversarial negative cases:** ten wrappers share writable singleton; old manager retains policy decisions; extracted methods compile but old lifecycle still owns cancellation; test mock only verifies constructor; concurrent migration produces two writers; stale observation still claims pass. Each must fail or force an explicit reduced-scope/blocked verdict.

Completion requires all mandatory scoped invariants, no unresolved blocking issue, current revision match, and evidence source distinct from the actor's unsupported assertion.
