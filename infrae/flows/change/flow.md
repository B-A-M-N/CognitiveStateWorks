---
flow: change
operations: [deploy, configuration_change, rotate_secret, node_replacement, upgrade, scale, migrate]
triggers: [mutation, change]
states:
  from: [PLANNED, CHANGING]
  through: [CHANGING]
framework_requirements: [fuse, ward]
required_specialists: []
optional_specialists: []
---
# Flow: Change (PLANNED → CHANGING → VERIFIED)

Purpose: planned mutation of running infrastructure — deployment, scaling,
network change, storage migration, certificate/secret rotation, node
replacement, configuration change, upgrade, service relocation.

## Pipeline

```text
ChangeRequested → ImpactAnalysis → BlastRadiusAnalysis → Preconditions
→ RollbackAnalysis → ObservabilityCheck → MutationGate → Execute → Observe
```

The MutationGate lives in `../../policies/mutation-gates/`; blast radius in
`../../primitives/blast-radius/`; reversibility hierarchy and rollback plans
in `../../primitives/rollback/`. Domain skills may be called for mechanics —
**this flow owns the transition**. A networking specialist knows how to
modify routing; it does not independently decide whether routing is safe to
modify.

## Execution rigor follows risk, not command complexity

- **LOW** — read-only monitoring, non-authoritative telemetry, disposable dev infra.
- **MODERATE** — replica count increase, adding a worker, bounded config update, backward-compatible revision deploy.
- **HIGH** — ingress behavior, trust boundaries, database topology, scheduler behavior, critical credential rotation, persistent-state migration.
- **CRITICAL** — deleting production state, replacing trust roots, global routing, storage ownership rewrite, authentication authority change, rollback-compatibility break, destructive schema/data migration.

CRITICAL: do not execute — isolate or recover first.

## Reversibility hierarchy

```text
read-only → additive → traffic shift → replaceable mutation
→ stateful mutation → destructive mutation
```

The lower the operation, the stronger its safeguards. Prefer: feature flags,
staged traffic shifting, immutable replacement, shadow infrastructure, dual
writes with verification, snapshot before migration, versioned config,
reversible DNS, canary. Never destroy previous valid state until the new
state proves viable.

## Rollout strategy by risk

- **Rolling** — versions coexist safely, capacity supports temporary reduction, rollback straightforward.
- **Canary** — only useful when traffic is representative + metrics are failure-sensitive + sample size is meaningful + abort conditions exist. Trivial traffic for 30 seconds proves nothing.
- **Blue/Green** — parallel environments feasible, fast switch valuable.
- **Shadow** — new behavior consumes mirrored traffic without authoritative effects.
- **Stop-and-replace** — downtime explicitly permitted, simplicity outweighs availability.

Rollout gates (stop automatically or operationally on failure): startup, readiness stability, error rate, latency, capacity, dependency health, no new saturation, no abnormal retries, no data inconsistency.

## Partial failure is expected

5 nodes targeted, 3 updated, 1 failed, 1 unreachable — the system is now
mixed. Design for mixed versions, partial propagation, partially rotated
secrets/schemas/data/DNS. A plan that assumes atomic infrastructure is
incomplete. Hand to `../validate/` — never self-certify from exit codes.
