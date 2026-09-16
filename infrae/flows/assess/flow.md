---
flow: assess
required_specialists: []
optional_specialists: []
---
# Flow: Assess (MODELED → ASSESSED)

Purpose: determine the condition of the modeled infrastructure.

## Ten dimensions — never one collapsed score

Produce findings under each:

```text
Correctness · Reliability · Security · Capacity · Performance
Recoverability · Observability · Operability · Complexity · Cost
```

A single "health = 73%" number destroys exactly the information operators
need.

## Readiness classification (overlay, derived from dimensions)

- **RED — Unsafe.** Unknown state ownership, known data-loss risk, no viable recovery, broken security boundary, uncontrolled destructive migration, cannot tolerate expected load.
- **ORANGE — Significant gaps.** Functional, but meaningful operational blockers remain (observability insufficient, restore untested, failover unknown, capacity margin unclear).
- **YELLOW — Operationally viable.** Usable with known bounded limitations; no immediate correctness or safety blockers.
- **GREEN — Production ready for a defined envelope.** Workload defined, dependencies and failure behavior understood, capacity validated, observability adequate, boundaries appropriate, deploy/recovery viable — **within the declared envelope only**.
- **BLUE — Frozen.** Intentionally unchanged pending a migration window, external dependency, approval, or maintenance window.

Preserve the underlying dimension findings even after classifying.

## Evidence standards during assessment

- A green dashboard is not observability; dashboard count is not coverage.
- Replication is not backup; a backup is not recovery until restore is tested.
- Test-infrastructure evidence must state what it proves given differences from production (topology, data volume, concurrency, latency, provider behavior). State clearly what is proven and what is not.
- Correlation is not root cause: a deploy preceding an outage is strong evidence, not proof. A CPU spike may be cause, effect, or unrelated symptom. Identify mechanism.

## Output

Findings per dimension + readiness class + explicit unknowns + required
evidence to close each blocking finding (see `../../STATEWORK.md` Standard
Review Output for the format).
