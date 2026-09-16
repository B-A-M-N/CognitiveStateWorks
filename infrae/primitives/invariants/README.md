# Primitive: Invariants

What must remain true across any legal transition.

## Form

Concrete, observable, falsifiable statements:

```text
At least two serving replicas remain available during rollout.
Untrusted clients can never directly address internal workers.
No acknowledged write may be lost during migration.
A single host failure must not make the control plane unavailable.
No workload may consume another workload's credentials.
Inference requests must retain bounded queue latency under expected peak load.
A backup must be restorable onto clean infrastructure.
```

Not: "the system stays healthy." Without an invariant, infrastructure work
becomes configuration churn.

## Role in the state machine

- Every `PLANNED → CHANGING` transition requires explicit invariants.
- `CHANGING → VERIFIED` requires the invariant observed true in *effective* state.
- An invariant violation from any state forces `DEGRADED` — that transition firing is the model working.
- New findings classify as in-scope (violates the current invariant → fix here) or out-of-scope (separate work).

## Paired invariants

Changes often have pairs: the target invariant (what becomes true) and the
preservation invariant (what must not become false). Validation checks both —
a migration that achieves cutover while breaking read-after-write has
satisfied the target and violated the preservation invariant.
