# Domain: Network

Supplies network analysis and actions to Infrae flows. Does not own state
transitions — a routing specialist knows how to modify routing; it does not
independently decide whether routing is safe to modify (that is the Change
flow + Mutation Gate).

## Covers

Routing, DNS, proxying, load balancing, firewalling, connectivity, TLS, MTU,
bandwidth, interfaces, subnets, NAT, ingress/egress, service discovery,
overlay networks, tunnels, latency, packet loss, connection limits.

## Key discipline

**Network failures frequently masquerade as application failures.** When
connectivity behavior is uncertain, inspect — in order — name resolution,
routing, reachability, firewall, NAT, proxy chain, TLS, MTU, connection
establishment, packet loss, latency, bandwidth, connection reuse, port
exhaustion. Do not jump directly to application logic.

## DNS

A DNS update is not instantaneous infrastructure state: TTL, resolver
caching, negative caching, split-horizon behavior, stale clients, propagation
delay all mean old state survives the change.

## Load balancing

Determine: algorithm, health source, connection persistence, session
affinity, draining behavior, backend capacity, fail-open/fail-closed
behavior. A load balancer can correctly distribute traffic into an unhealthy
system if health semantics are weak.

## Partitions

Distinguish `node failed` from `node unreachable from this observer`. A
partition can create two systems that both believe the other side is dead —
design ownership and failover accordingly.

## Proxy and trust boundaries

Distinguish physical peer, trusted proxy, forwarded identity, and
application client identity. Never trust forwarded metadata solely because a
header exists — trust must derive from an authenticated or explicitly trusted
boundary (details in `../security/`).

## MTU and bandwidth

MTU mismatches produce intermittent, protocol-dependent failures that look
like application hangs; verify path MTU when behavior is size-dependent.
Bandwidth saturation produces latency and retries before it produces visible
errors — measure utilization on the path, not at the endpoints only.
