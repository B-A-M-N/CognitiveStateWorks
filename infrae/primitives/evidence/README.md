# Primitive: Evidence

What observation proves, at what strength, packaged for handoff.

## Strength ladder (weakest → strongest)

```text
1. code/config exists
2. command executed successfully
3. generic tests pass
4. targeted checks pass
5. failure reproduces before, passes after
6. boundary/failure cases pass
7. realistic integration evidence
8. production-equivalent workload evidence
```

A successful command proves only that the command succeeded. Use the level
appropriate to the claim; do not overclaim from weak evidence, and do not
fabricate evidence that was not collected.

## Declared vs effective

Every claim about state should say which state it is about. `Terraform
applied` is evidence about declared state; it is weak evidence about
effective state. Evidence about production from test infrastructure must
state the material differences (topology, data volume, concurrency, latency,
provider behavior) and what that leaves unproven.

## Failure testing converts claims into evidence

A resilience property that has never been failure-tested is a claim. Restore
never exercised is a hope. Failure evidence lives at rungs 5–8; nearly all
infrastructure claims that matter (redundancy, recovery, capacity under
failure) require them.

## Infrastructure Evidence Packet

For meaningful infrastructure work, report enough for another engineer to
understand the result:

```yaml
objective:    { problem: invariant: }
environment:  { scope: topology: }
change:       { previous_state: intended_state: actual_state: }
risk:         { blast_radius: failure_domains: data_risk: security_risk: }
capacity:     { baseline: observed: headroom: }
validation:   { functional: integration: performance: failure: recovery: }
rollback:     { mechanism: tested: }
observability:{ relevant_metrics: alerts: }
residual_risk:{ known: unknown: }
status:       { readiness: next_action: }
```

Unknown values are reported as unknown. This packet is the handoff contract
(element 13) to other flows, StateWorks (Getter for landing, Gitter for the
repository side), or the operator.
