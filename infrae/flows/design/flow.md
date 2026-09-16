---
flow: design
required_specialists: []
optional_specialists: []
---
# Flow: Design (→ PLANNED, for new or restructured infrastructure)

## Subflow

```text
requirements → workload → invariants → state ownership → topology
→ dependencies → failure domains → capacity → security boundaries
→ observability → deployment → recovery → design evidence
```

## Major guard

> A design cannot be considered complete if it models the happy path but not
> failure and recovery.

## Design content

- **Invariants** (`../../primitives/invariants/`) — what must remain true, stated concretely.
- **Workload shape** — steady state, peak, burst, growth. Capacity is evaluated against workload shape, never raw totals.
- **State ownership** — one authoritative owner per critical datum; ambiguous ownership causes split brain, lost writes, stale reads. If several systems may modify the same state, arbitration must be explicit.
- **Failure domains and redundancy** (`../../primitives/failure-domain/`) — the redundancy test: replica count + failure-domain separation + state independence + routing + health detection + failover + post-failure capacity.
- **Capacity envelope** (`../../domains/capacity/`) — with failure/deployment/recovery headroom. A system consuming 100% of resources under normal load has no operational reserve.
- **Security boundaries** (`../../domains/security/`) — trusted/untrusted callers, authn/authz, credential scope; conscious fail-open vs fail-closed policy.
- **Observability** (`../../domains/observability/`) — able to answer what/where/when/who/what-changed/which-dependency/is-it-spreading/did-recovery-occur.
- **Deployment model** — rolling / canary / blue-green / shadow / stop-and-replace chosen by risk, not fashion.
- **Recovery model** — rollback or forward recovery, restore-tested.
- **Complexity budget** — every new proxy/queue/cache/mesh/controller adds a failure mode, config surface, dependency, observability requirement, and upgrade path. Require a concrete problem before adding infrastructure. "Architecturally mature looking" is not a requirement.
- **Service boundaries** — a useful boundary has independent ownership, lifecycle, scaling, failure behavior, deployment, state, security policy, or performance profile. Components that always change/scale/fail together and share state may gain nothing from separation. A distributed God Object is still a God Object.

## Testing layers to specify

Static (config/schema/IaC plan) → component → integration → topology → load → failure → migration → recovery. Passing only static checks is weak evidence.

## Operational readiness review

Before calling the design production-ready, assess: architecture (topology/dependencies/ownership known), reliability (failure domains/redundancy validated/degradation defined), capacity (normal + peak validated, headroom present), security (boundaries/secrets/least privilege), observability, operations (deploy/rollback/incident/backup/restore/migration/decommission), evidence (integration/load/failure/recovery), known_gaps.
