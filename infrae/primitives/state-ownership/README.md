# Primitive: State Ownership

Who owns each piece of authoritative state, and which state is effective.

## The six states of state

```text
DECLARED STATE    what configuration says should exist
OBSERVED STATE    what actually exists
EFFECTIVE STATE   what the running system is actually using
DEPENDENCY STATE  what surrounding systems assume exists
FAILURE STATE     what happens when something stops working
RECOVERY STATE    what can actually be restored and how
```

These may disagree. The disagreement is itself an infrastructure finding:

```text
Terraform says 3 replicas
Kubernetes says 3 desired replicas
2 pods are Running
1 pod is crash-looping
load balancer has only 1 healthy endpoint
```

Declared: 3. Effectively serving: 1. Infrae reasons from **effective
reality**, not desired configuration alone.

## Single source of truth

For every critical datum, one authoritative ownership model. Ambiguous
ownership causes split brain, lost writes, stale reads, reconciliation
ambiguity. If several systems may modify the same state, define arbitration
explicitly.

## Drift and authority

When declared and effective state diverge, determine before reconciling:
is runtime authoritative? Is code authoritative? Was the drift intentional?
Will reconciliation destroy needed state? Do not blindly reapply desired
state if production contains a necessary emergency divergence. Understand
first.

## Ownership and authority

State ownership answers "who owns this data"; mutation authority answers
"who may change it." Both must be explicit before mutation. Unknown ownership
→ additive or isolated action only. In multi-agent work, record current
effective state before modification and re-observe before each critical
mutation (`policies/concurrency/`).
