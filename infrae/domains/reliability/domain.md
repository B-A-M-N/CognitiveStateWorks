# Domain: Reliability

Supplies reliability analysis and actions to Infrae flows. Does not own state
transitions — a retry specialist knows how to configure backoff; whether the
retry topology amplifies an outage is the Model flow's dependency-graph
finding.

## Covers

Redundancy, availability, failure domains, retries, timeouts, circuit
breakers, backpressure, failover, graceful degradation, overload behavior,
recovery objectives.

## Redundancy test

Do not accept "we have N replicas" as proof of resilience. Evaluate:

```text
replica count + failure-domain separation + state independence
+ routing behavior + health detection + failover behavior
+ capacity after failure
```

Details in `../../primitives/failure-domain/`.

## Retry discipline

Retries can amplify outages. For every retrying dependency define: max
attempts, timeout, backoff, jitter, retryable vs non-retryable errors, and an
overall deadline. Watch for retry multiplication:

```text
client retries + gateway retries + service retries + database retries
```

can turn one request into many — precisely when the dependency can least
afford it.

## Timeout discipline

Every remote dependency should have a bounded wait: connection, request,
overall deadline, queue, idle. Nested components must not have contradictory
timeout hierarchies — a downstream timeout longer than the caller's total
deadline wastes work.

## Circuit breaking

When a dependency fails continuously, prevent unlimited calls into it — but
circuit breakers need careful recovery behavior (probe-before-close), and
they are not a substitute for fixing overload or dependency architecture.

## Backpressure

Systems need an explicit overload policy: queue, reject, shed low-priority
work, throttle, degrade quality, redirect, delay admission. Do not let
uncontrolled retry behavior become the overload policy.

## Graceful degradation

Classify capabilities as CRITICAL (purpose fails without them), IMPORTANT
(temporary degradation acceptable), OPTIONAL (disablable under stress).
Degradation options: disable expensive analytics, reduce model quality,
reject low-priority requests, serve stale cache, disable optional
integrations. Degradation should be designed, not discovered during the first
incident.

## Failure testing

For critical infrastructure, test failure intentionally: kill worker/host,
block dependency, inject latency, exhaust quota, break DNS, restart control
plane, remove replica, simulate disk pressure, expire credentials, interrupt
migration. The objective is to validate claimed resilience — not chaos for
entertainment. All failure testing passes the Failure Injection Gate
(`../../policies/destructive-change/`).

## Recovery objectives

Where applicable define RPO and RTO — and measure them, don't assert them.
Recovery completion is defined by the Recover flow's full completion
condition (service + integrity + redundancy + capacity + monitoring), never
by liveness alone.
