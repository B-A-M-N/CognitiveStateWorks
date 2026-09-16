# Domain: Capacity

Supplies capacity analysis to Infrae flows — especially Assess (saturation
findings) and Scale (bottleneck location). Does not own state transitions —
a capacity specialist identifies the constrained resource; whether to add
capacity is the Scale flow's call after the bottleneck rule is satisfied.

## Covers

Headroom, saturation, queue growth, concurrency, throughput, latency,
memory/CPU pressure, accelerator utilization, network saturation, storage
saturation, quota exhaustion.

## Key discipline

**Raw resource totals are insufficient.** Capacity depends on workload,
concurrency, resource locality, contention, scheduler behavior, memory
behavior, network behavior, storage behavior, and failure reserve.

## Capacity envelope

```yaml
workload:  { steady_state: peak: burst: growth: }
compute:   { cpu_per_unit: memory_per_unit: accelerator_per_unit: }
network:   { ingress_rate: egress_rate: bandwidth_peak: }
storage:   { capacity: growth_rate: iops: throughput: }
service:   { concurrency: queue_limit: timeout: max_throughput: }
reserve:   { failure_headroom: deployment_headroom: recovery_headroom: }
```

A system designed to consume 100% of resources under normal conditions has
no operational reserve.

## Headroom

Capacity planning must account for node loss, rolling deployment, failover,
traffic burst, retry traffic, compaction, replication, backup, recovery,
rebalancing, noisy neighbors. Headroom is not wasted capacity — it is
resilience capacity. Do not optimize cost by removing the headroom required
to meet reliability requirements; do not solve every capacity problem by
buying more before identifying the real bottleneck.

## Queueing

Queues hide overload until they explode latency. Track arrival rate, service
rate, queue depth, queue wait, worker utilization, drop/rejection behavior.
If arrival rate exceeds sustained service rate, the queue grows without bound
unless backpressure or rejection occurs — autoscaling cannot always solve
this quickly enough.

## Distributed resource topology

Aggregated resources do not form one coherent pool. For distributed compute:
per-node RAM and accelerator memory, interconnect speed and latency,
serialization cost, transfer volume, workload partitionability, scheduling,
synchronization. `16 + 8 + 4 GB VRAM` ≠ 28 GB unified VRAM unless the
application explicitly supports distributed placement and its communication
cost.

## Locality

For data-heavy or model-heavy systems, locality can dominate performance:
cached model weights, KV cache, dataset shards, storage locality, accelerator
residency, hot database pages. Moving work may cost more than queueing
briefly where the state already exists. Treat locality as measurable
evidence, not assumed benefit.

## Quota exhaustion

Shared quotas (API rate limits, connection limits, provider quotas) are
capacity constraints invisible in resource metrics until they fire. Track
quota headroom as first-class capacity, and treat quota exhaustion as a
saturation finding, not an application bug.
