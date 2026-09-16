# Domain: Compute

Supplies compute analysis and actions to Infrae flows. Does not own state
transitions — a scheduling specialist knows how to place work; it does not
independently decide whether placement is safe.

## Covers

- Hosts, CPUs, accelerators (GPU), NUMA topology, memory behavior
- Virtual machines, containers, process placement, resource isolation
- Scheduling, heterogeneous nodes, resource overcommit
- Hardware capability, host lifecycle

## Key discipline

**Resource totals are not capacity.** `256 GB total RAM` does not mean a
200 GB workload runs safely if no individual node provides sufficient usable
memory. `24 GB + 12 GB GPU memory` does not necessarily provide a flat 36 GB
address space. Resource topology matters — see `../../primitives/topology/`.

## Scheduling constraints

A scheduler should consider: resource availability, locality, affinity,
anti-affinity, priority, failure domains, hardware capability, persistent
state, network topology. Round-robin is not universally correct scheduling.

## Heterogeneous compute

Mixed hardware requires capability-aware placement: architecture, instruction
set, accelerator vendor and capability, memory capacity, driver version,
network and storage performance. Do not assume the slowest or smallest node is
equivalent to the largest.

## Resource isolation

Workloads can starve each other through CPU, memory, GPU/VRAM, file
descriptors, process count, connection pools. Isolation boundaries should
match workload risk; investigate noisy-neighbor effects through per-workload
utilization, memory pressure, scheduling behavior, and accelerator occupancy.

## Host lifecycle

Host replacement, kernel upgrades, and reboots are capacity and failure-domain
events, not administrative trivia: drain behavior, capacity during transition,
and failure-domain rebalancing after the node returns.
