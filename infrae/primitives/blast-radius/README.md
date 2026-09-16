# Primitive: Blast Radius

What a change (or failure) can break, and how far failure can propagate.

## Classification

```text
LOCAL    — one isolated process or disposable node
BOUNDED  — one service or small tenant subset
BROAD    — multiple dependent services or substantial traffic
SYSTEMIC — control plane, identity, shared storage, shared routing,
           global secrets, global network, or a common dependency
```

Higher blast radius demands stronger evidence and safer rollout — execution
rigor follows risk, not command complexity.

## Questions before meaningful change

```text
What can this change break?
How many users/services/nodes?
Can failure propagate? Can it damage persistent state?
Can it lock operators out? Can it invalidate rollback?
Can it exhaust shared resources? Cause retry amplification?
Can it create a security exposure?
```

## Blast radius includes the transition, not just the endpoint

A change whose end state is safe can still be dangerous mid-flight: capacity
during a rolling replacement, credential old/new overlap windows, DNS
propagation, dual-state migration coexistence, mixed versions. Ask what the
blast radius is *at the worst moment of the transition*.

## Relationship to failure domains

Blast radius is what your change can break; failure domains are what reality
can break. A change touches a failure domain boundary when it modifies: shared
storage, control plane, identity, routing, DNS, trust roots, deployment
pipeline — these are automatically at least BROAD, often SYSTEMIC.
