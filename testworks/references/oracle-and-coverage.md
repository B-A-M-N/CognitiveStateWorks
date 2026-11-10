# Oracle and fault-detection catalogue

Use these patterns where their underlying risk exists, not as a mandatory
checklist. A useful oracle detects a plausible wrong behavior; asserting only
that a function returned or a command exited is usually weak.

- **Example-based:** approved expected outputs for representative classes.
- **Boundary:** null, empty, extreme, overflow, limits, timeout, resource bound.
- **Negative/security:** unauthorized action rejected, isolation retained,
  integrity enforced, replay rejected, error paths fail closed.
- **Stateful:** legal and illegal lifecycle transitions, concurrency invariants,
  restart/retry idempotence, crash recovery, cross-request contamination.
- **Contract:** wire/API/schema compatibility and negative violation behavior.
- **Property/metamorphic:** invariants across generated inputs or transformations,
  with reproducible seeds and counterexample minimization.
- **Differential/mutation:** comparison with a trusted baseline or deliberately
  broken implementation to prove the assertion is sensitive to a real defect.
- **Performance/load:** latency quantiles, throughput under controlled concurrency,
  correctness at pressure, telemetry quality and resource use; preserve workload
  fingerprints and do not compare unlike prefill/streaming regimes.

Coverage percentages may guide exploration but do not prove oracle sensitivity
or protect the right risks.
