# Primitive: Health Model

Health is multi-dimensional; collapsing it into one boolean destroys
operational information.

## Dimensions

```text
PROCESS HEALTH        Is the process alive?
READINESS             Should it receive new work?
DEPENDENCY HEALTH     Can it reach required dependencies?
FUNCTIONAL HEALTH     Does meaningful work succeed?
CAPACITY HEALTH       Can it handle current load?
DEGRADED HEALTH       Is it operating with reduced capability?
CONTROL-PLANE HEALTH  Can it still be managed?
DATA HEALTH           Is state consistent and durable?
```

A process can be alive while functionally broken. A service can pass its
readiness probe while its dependency is dead. Health dimensions map to
distinct failure modes and distinct recovery actions — liveness tells you to
restart; functional health tells you whether restarting will help (usually
not).

## Probes must test what they claim

```text
Bad:  HTTP server responds → system healthy

Better:
  process alive
  + critical initialization complete
  + required dependency reachable
  + service able to perform representative operation
  + capacity not catastrophically exhausted
```

Do not make probes so expensive that probing causes failure.

## Health semantics propagate

A load balancer can correctly distribute traffic into an unhealthy system if
health semantics are weak. Readiness gates, failover triggers, and rollout
gates all inherit the fidelity of the underlying health model — weak health
checks make every downstream automation confidently wrong.

## Relation to Assess

The Assess flow produces findings across ten dimensions and never collapses
them into one score. Health-model dimensions feed those findings; the
distinction exists for the same reason.
