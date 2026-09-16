# Domain: Observability

Supplies observability analysis and actions to Infrae flows. Does not own
state transitions — an alerting specialist knows how to configure alerts;
whether the system is observable *enough to mutate safely* is the Change
flow's ObservabilityCheck.

## Covers

Metrics, logs, traces, events, health probes, alerting, SLOs, dashboards,
diagnostics, audit evidence, cardinality discipline.

## Key discipline

**Observability is not dashboard count.** A production system should expose
enough information to answer:

```text
What is happening?        Where is it happening?
When did it start?        Who or what is affected?
What changed?             Which dependency is failing?
Is the failure spreading? Are retries making it worse?
What resource is saturating?
What request path produced the failure?
Did recovery actually occur?
```

A green dashboard proves the dashboard is green.

## Metrics

Measure the constraint that actually governs capacity, across:

- **Traffic** — request rate, throughput, concurrency, queue depth
- **Errors** — failure/timeout/retry/rejection rates, status distribution
- **Latency** — p50/p95/p99, tail latency, queue wait, service time
- **Saturation** — CPU, memory, GPU/VRAM, disk, IOPS, network, connection pools, worker slots, queue limits
- **Availability** — healthy replicas, ready replicas, failed nodes, quorum state
- **State** — replication lag, cache state, data lag, pending migrations, backlog

## Cardinality discipline

Observability itself can destroy infrastructure. Never use as metric
dimensions: raw user IDs, request IDs, arbitrary URLs, entire error strings,
dynamically generated identifiers. Logs/traces carry high-cardinality detail;
metrics carry bounded aggregation.

## Logs

Logs should answer operational questions: timestamp, service, instance,
correlation ID, operation, dependency, outcome, latency, error category,
retry attempt. Never casually log secrets, bearer tokens, passwords, private
keys, or sensitive request bodies.

## Tracing

Use when latency or failures cross several services. Trace boundaries should
expose ingress, routing, queue, dependency calls, storage, worker execution,
egress. Tracing without meaningful span boundaries is decorative telemetry.

## Alerts

Alert on actionable conditions. `CPU > 70%` without workload context is not
actionable; `sustained saturation + growing queue + latency/error impact` is.
Every alert should answer: what is wrong, why does it matter, what should the
operator inspect first.

## SLOs

Where appropriate define SLI (what is measured), SLO (the objective), and
error budget (tolerable failure). Candidates: availability, successful
completion, p95 latency, queue delay, write durability, replication
freshness. Do not invent arbitrary SLOs because the terminology sounds
mature — they must reflect actual operational requirements.

## Health model and probes

Health is multi-dimensional: process, readiness, dependency, functional,
capacity, degraded, control-plane, data. Health checks must test what they
claim — an HTTP 200 is not system health. Better: process alive + critical
initialization complete + required dependency reachable + representative
operation succeeds + capacity not catastrophically exhausted. Do not make
probes so expensive that probing causes failure. Details in
`../../primitives/health-model/`.
