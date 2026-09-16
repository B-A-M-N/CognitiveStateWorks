# Primitive: Rollback

The planned path back — or forward — from a mutation.

## Reversibility hierarchy

```text
read-only → additive → traffic shift → replaceable mutation
→ stateful mutation → destructive mutation
```

The lower the operation, the stronger its safeguards. Prefer: feature flags,
staged traffic shifting, immutable replacement, shadow infrastructure, dual
writes with verification, snapshot before migration, versioned configuration,
reversible DNS, canary. Never destroy previous valid state until the new
state proves viable.

## "Can roll back" is not a rollback plan

A real rollback plan specifies:

```yaml
trigger:      abort conditions that fire it
mechanism:    exact commands or actions
dependencies: required old state (does the change destroy it?)
data:         compatibility and loss risk
timing:       expected recovery path and duration
verification: success conditions
failure:      what happens if the rollback itself fails
```

Question 10 of the Change Gate: **can rollback itself fail?** A rollback that
requires old state the change destroyed is not a rollback plan.

## Forward recovery

For irreversible operations, define forward recovery instead: what makes the
system safe when there is no way back. Same structure — trigger, mechanism,
verification, failure-of-the-failure-plan.

## Relationship to the Change Gate

The gate asks "what happens if this operation stops halfway?" Partial
application is a rollback scenario; mixed state is the default outcome of
distributed mutation, not an exception (see the Change flow).
