# Test selection and exit examples

| Change situation | Default decision | Explicit exception |
| --- | --- | --- |
| Comment-only change, tests unrelated, stable old evidence | Decline additional tests with scope | Documentation compiles into behavior |
| Isolated parser change | Boundary/unit/contract subset | Shared format contract may require consumers |
| Shared auth/ownership layer | Negative auth, integration, concurrency | No skipping control gates for cost |
| Existing regression reproduces new defect | Repair and run targeted | Full suite only if scope expands |
| Suite cost is bottleneck | Split fast and release gates, parallelize safely | Do not delete critical coverage |
| Flaky test with unclear cause | INCONCLUSIVE; diagnose | Not PASS due to lucky retry |
| Test modified since prior receipt | Invalidate affected evidence | Prove equivalence with current test code before reuse |
| Release workload changed | Re-run workload-dependent gates | Independent unit receipts may remain valid |

A legitimate NO_ADDITIONAL_TESTING_NEEDED decision says *why* a particular
additional test or run cannot improve the decision enough to justify its cost;
it does not mean "testing is unnecessary" globally.
