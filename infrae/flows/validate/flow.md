---
flow: validate
operations: [validate, verify]
triggers: [validation, validate]
states:
  from: [CHANGING, VERIFIED]
  through: [VERIFIED]
framework_requirements: [owl, anchor]
required_specialists: []
optional_specialists: []
---
# Flow: Validate (CHANGING → VERIFIED)

Purpose: prove the mutation produced the intended **effective** state. This
flow exists because validation is not an afterthought:

```text
agent changed something ≠ thing is correct
```

## Questions

```text
Did the mutation execute?
Did declared state change?
Did effective state change?
Did the invariant become true?
Did another invariant become false?
Did performance regress?
Did blast radius remain bounded?
Did dependencies remain healthy?
Can the system still recover?
```

## Health verification is multi-dimensional

Do not collapse health into one boolean. Verify the health model dimensions
that the invariant depends on (`../../primitives/health-model/`): process
alive ≠ ready ≠ dependency-reachable ≠ functionally working ≠ capacity-adequate.
A process can be alive while functionally broken; a load balancer can
correctly distribute traffic into an unhealthy system if health semantics are
weak.

## Evidence thresholds

Match evidence strength to claim (`../../policies/evidence-thresholds/`).
A successful command proves only that the command succeeded. For capacity
claims, load evidence; for resilience claims, failure evidence; for recovery
claims, a tested restore.

## Post-change verification checklist

Traffic recovered · errors normalized · latency normalized · queues drained ·
replication healthy · capacity restored · data consistent · credentials valid
· alerts cleared **for the right reason**.

## On failure

Any failed check → `DEGRADED` (this transition is the model working, not the
work failing) → hand to `../recover/` or `../incident/`. Do not stack
compensating mutations on an unverified state.
