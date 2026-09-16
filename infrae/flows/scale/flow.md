---
flow: scale
required_specialists: []
optional_specialists: []
---
# Flow: Scale (capacity transitions)

## Pipeline

```text
observe workload → locate bottleneck → determine constrained resource
→ model scale response → check dependency capacity
→ add/remove capacity → validate throughput + latency + saturation
```

## The bottleneck rule

> Do not scale before identifying the actual bottleneck.

System throughput is bounded by its most constrained relevant stage. Adding
capacity to a non-bottleneck stage may produce no improvement. Before scaling
determine: where requests wait, what resource saturates, what dependency
throttles, what queue grows. Otherwise agents throw replicas at database
bottlenecks, network bottlenecks, quotas, and lock contention.

## Performance decomposition

Latency is not one mysterious number:

```text
DNS + connection + TLS + queue + routing + service + dependency
+ storage + response transfer
```

Measure components.

## Capacity engineering

Raw totals are insufficient. Capacity depends on workload, concurrency,
resource locality, contention, scheduler, memory/network/storage behavior,
and failure reserve.

- `256 GB total RAM` ≠ a 200 GB workload runs safely if no single node has enough usable memory.
- `24 GB + 12 GB GPU memory` ≠ a flat 36 GB address space. Distributed resource topology is not a unified pool — interconnect speed, serialization cost, transfer volume, workload partitionability, and synchronization all bound it.

## Capacity envelope

```yaml
workload:  { steady_state: peak: burst: growth: }
compute:   { cpu_per_unit: memory_per_unit: accelerator_per_unit: }
network:   { ingress_rate: egress_rate: bandwidth_peak: }
storage:   { capacity: growth_rate: iops: throughput: }
service:   { concurrency: queue_limit: timeout: max_throughput: }
reserve:   { failure_headroom: deployment_headroom: recovery_headroom: }
```

## Headroom

Account for node loss, rolling deployment, failover, traffic burst, retry
traffic, compaction, replication, backup, recovery, rebalancing, noisy
neighbors. Headroom is not wasted capacity — it is resilience capacity.

## Queueing and backpressure

Queues hide overload until they explode latency. Track arrival rate, service
rate, depth, wait, utilization, drop behavior. If arrival > sustained service
rate, the queue grows without bound unless backpressure or rejection occurs —
autoscaling is usually too slow. Every system needs an explicit overload
policy: queue, reject, shed, throttle, degrade, redirect, or delay admission.
Never let uncontrolled retry behavior become the overload policy.

## Cost

Cost is a constraint: baseline, peak, idle, storage growth, egress,
redundancy, observability, failover reserve. Do not remove the headroom
reliability requires; do not buy infrastructure before finding the real
bottleneck.

## Heterogeneous infrastructure

Mixed hardware requires capability-aware placement: architecture, instruction
set, accelerator vendor/capability, memory, drivers, network, storage. The
smallest node is not equivalent to the largest. For data/model-heavy systems,
locality can dominate performance (cached weights, KV cache, dataset shards,
accelerator residency) — moving work may cost more than queueing where the
state already lives.
