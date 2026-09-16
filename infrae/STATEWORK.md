---
name: infrae
description: >
  Infrastructure StateWork. Use whenever work affects infrastructure topology,
  availability, capacity, performance, trust boundaries, failure domains,
  production configuration, orchestration, deployment, service dependencies,
  stateful systems, networking, secrets, infrastructure-as-code, monitoring,
  incident response, or operational readiness. Infrae requires infrastructure
  truth to be established before mutation and treats resilience, rollback,
  observability, blast radius, and failure behavior as first-class design
  constraints. Vendor-neutral: it governs the engineering discipline beneath
  AWS/GCP/Kubernetes/Terraform/etc., not any implementation. Routing: state
  questions (what state is this system in, is this change legal, what evidence
  permits mutation) start at STATEWORK.md; domain specialists live in
  domains/, recurring state concepts in primitives/, hard gates in policies/.
---

# Infrae — Infrastructure StateWork

Infrae governs **infrastructure state**: what state a system is in, which
transitions are legal, what evidence permits mutation, what invalidates the
state, and how to recover. It implements the CognitiveStateWork protocol
(`../PROTOCOL.md`) for infrastructure. Domain knowledge lives in `domains/`,
recurring state concepts in `primitives/`, and hard gates in `policies/` —
this document is the state machine and the index into them.

---

## Core Doctrine

> Infrastructure must be reasoned about as a system of dependencies, resources,
> trust boundaries, failure domains, and state transitions.

A system being reachable does not prove it is healthy. A deployment succeeding
does not prove it is safe. A service returning `200 OK` does not prove it is
functioning correctly. A redundant component does not prove the system is
redundant. A backup existing does not prove recovery works. A monitoring
dashboard being green does not prove the system is observable. A configuration
being committed does not prove production matches it. A test passing in
isolation does not prove the production topology behaves the same way.

Never reduce infrastructure engineering to:

```text
deploy → command succeeded → done
```

---

## Protocol instantiation

Implements the 13-element CognitiveStateWork protocol for infrastructure:

**1. Domain.** Compute, networking, storage, identity/trust, deployment,
reliability, capacity, observability, and operations — at any scale from a
laptop dev environment to multi-region fleets. Vendor-neutral. Does not own
application feature design, product requirements, source-control mechanics,
or PR policy (those belong to application architecture and other StateWorks);
it may surface their infrastructure implications.

**2. State vocabulary.** `UNKNOWN, OBSERVED, MODELED, ASSESSED, PLANNED,
CHANGING, VERIFIED, STABLE, DEGRADED, RECOVERING, BLOCKED, INCIDENT,
RETIRED`. Production readiness is tracked as an overlay classification:
`RED / ORANGE / YELLOW / GREEN / BLUE` (green applies only to a declared
operating envelope, never universally).

**3. State observations.** Distinguish declared / observed / effective /
dependency / failure / recovery state — these may disagree, and the
disagreement is itself a finding. Terraform says 3 replicas, Kubernetes says
3 desired, 2 pods Running, 1 healthy endpoint: declared 3, effectively
serving 1. Reason from effective reality. Observation must not silently mutate
the thing observed.

**4. Invariants.** Every task identifies what must remain true ("at least two
serving replicas during rollout," "no acknowledged write lost during
migration," "untrusted clients never address internal workers," "a backup
restorable onto clean infrastructure"). Without an invariant, infrastructure
work is configuration churn. See `primitives/invariants/`.

**5. Allowed transitions.** The state machine below. Anything not listed is
illegal.

**6. Transition guards.** The Change Gate (`policies/mutation-gates/`),
the Failure-Injection Gate, and the Decommission checklist. Guards are
answered by evidence about effective state, not by how easy the command looks.

**7. Evidence requirements.** Strength must match the claim (see
`policies/evidence-thresholds/`). "Works on my machine," a green dashboard,
and a successful deploy each prove less than they appear to.

**8. Mutation authority.** Multi-agent rules in `policies/concurrency/`:
ownership boundaries, no overlapping control of the same mutable resource,
re-observe before each critical mutation. Unknown ownership → additive or
isolated action only.

**9. Invalidation rules.** Operator observations ("latency spikes under load,"
"the backup isn't actually usable," "we're still getting 429s") are evidence
that the infrastructure model may be incomplete → invalidate assumptions,
inspect effective state, determine mechanism. Never respond "the
configuration looks correct, therefore the observation must be wrong."

**10. Failure states.** `DEGRADED, BLOCKED, INCIDENT` are first-class states,
not prose. Partial failure is the expected shape of distributed failure —
design for mixed versions, partial propagation, partially rotated secrets,
partially migrated data.

**11. Recovery transitions.** `DEGRADED → RECOVERING → STABLE` and
`INCIDENT → RECOVERING → STABLE`, with completion defined as service
restored **plus** state integrity verified **plus** required redundancy
restored **plus** capacity restored **plus** monitoring normal — never merely
"HTTP 200 again." Restart is a mitigation, not a diagnosis.

**12. Completion states.** `STABLE` requires verified invariants;
`RETIRED` requires the decommission checklist (`flows/decommission/`);
readiness `GREEN` requires a declared operating envelope. Unknowns are
acceptable; hidden unknowns are not.

**13. Handoff contracts.** The Infrastructure Truth Packet (below),
Infrastructure Evidence Packet (`primitives/evidence/`), and Standard
Incident Output (`flows/incident/`) — each structured so another engineer can
reconstruct the state.

---

## The Infrae state machine

```text
          ┌─────────────┐
          │   UNKNOWN   │
          └──────┬──────┘
                 │ discover
                 ▼
          ┌─────────────┐
          │  OBSERVED   │
          └──────┬──────┘
                 │ model
                 ▼
          ┌─────────────┐
          │   MODELED   │
          └──────┬──────┘
                 │ assess
                 ▼
          ┌─────────────┐
          │  ASSESSED   │
          └──────┬──────┘
                 │ plan
                 ▼
          ┌─────────────┐
          │   PLANNED   │
          └──────┬──────┘
                 │ gated mutation
                 ▼
          ┌─────────────┐
          │  CHANGING   │
          └──────┬──────┘
                 │ observe result
          ┌──────┴───────┐
          ▼              ▼
    ┌──────────┐   ┌───────────┐
    │ VERIFIED │   │ DEGRADED  │
    └────┬─────┘   └─────┬─────┘
         │               │
         ▼               ├── recover
    ┌──────────┐         ▼
    │  STABLE  │◄──│ RECOVERING │
    └──────────┘   └────────────┘

Exceptional transitions (from ANY state):

  runtime observation invalidation        → OBSERVED
  dependency / topology inference invalidated → MODELED
  risk / readiness assessment invalidated → ASSESSED
  invariant violation                     → DEGRADED
  unknown ownership                       → BLOCKED
  unacceptable risk                       → BLOCKED
  catastrophic failure                    → INCIDENT
```
Invalidation is a deterministic epistemic downgrade, not a generic
"reassess": it returns state to the earliest level whose evidence remains
trustworthy. A runtime observation that invalidates current observation
reopens `OBSERVED`; invalidated dependency/topology inference reopens
`MODELED`; invalidated risk/readiness assessment reopens `ASSESSED`. The
downgrade target tells the agent exactly what remains trusted.

### Transition guards (summary)

| Transition | Guard |
|---|---|
| `UNKNOWN → OBSERVED` | Read-only discovery completed; nothing mutated during discovery |
| `OBSERVED → MODELED` | Declared/observed/effective state compared; disagreements recorded as findings |
| `MODELED → ASSESSED` | Findings across the ten dimensions (correctness, reliability, security, capacity, performance, recoverability, observability, operability, complexity, cost) — never one collapsed score |
| `ASSESSED → PLANNED` | Invariants explicit; blast radius classified; rollback or forward-recovery defined; observability sufficient to detect partial failure |
| `PLANNED → CHANGING` | Change Gate passed (`policies/mutation-gates/`); authority established |
| `CHANGING → VERIFIED` | Effective state observed to match intent; no critical regression; dependency health acceptable |
| `CHANGING → DEGRADED` | Invariant violated or partial failure detected — this transition is a **success** of the model, not a failure of the work |
| `DEGRADED/INCIDENT → RECOVERING → STABLE` | Full recovery definition above; "service started" is not recovery |

Flows are the procedures that move the domain through these transitions. Each
flow names the states it serves:

| Flow | Serves | One-line purpose |
|---|---|---|
| [`discover`](flows/discover/flow.md) | UNKNOWN → OBSERVED | Establish infrastructure truth without mutating it |
| [`model`](flows/model/flow.md) | OBSERVED → MODELED | Turn observations into topology/dependency/trust/failure graphs; surface declared≠effective |
| [`assess`](flows/assess/flow.md) | MODELED → ASSESSED | Findings across ten dimensions; readiness classification |
| [`design`](flows/design/flow.md) | → PLANNED (new infra) | Requirements → invariants → topology → failure → recovery; happy-path-only designs are incomplete |
| [`change`](flows/change/flow.md) | PLANNED → CHANGING → VERIFIED | Gated mutation of running infrastructure |
| [`validate`](flows/validate/flow.md) | CHANGING → VERIFIED | Prove the mutation produced the intended *effective* state |
| [`incident`](flows/incident/flow.md) | any → INCIDENT → RECOVERING | Detect, bound, stabilize, preserve evidence, restore — diagnose separately |
| [`recover`](flows/recover/flow.md) | DEGRADED/INCIDENT → STABLE | Restore redundancy, integrity, and capacity — not just liveness |
| [`migrate`](flows/migrate/flow.md) | multi-state transitions | Dual-state coexistence; the migration state machine |
| [`scale`](flows/scale/flow.md) | capacity transitions | Locate the bottleneck before adding anything |
| [`decommission`](flows/decommission/flow.md) | any → RETIRED | Removal as a production change; may legally end in BLOCKED |

## Domains (specialists invoked by flows)

| Domain | Covers |
|---|---|
| [`compute`](domains/compute/domain.md) | CPU, memory, accelerators/GPU, NUMA, virtualization, containers, scheduling, heterogeneous compute |
| [`network`](domains/network/domain.md) | Routing, DNS, proxying, load balancing, firewalling, connectivity, TLS, MTU, bandwidth |
| [`storage`](domains/storage/domain.md) | Durability, backup/restore, replication, filesystems, block/object, databases, storage pressure |
| [`identity`](domains/identity/domain.md) | Service/machine identity, credentials, certificates, secret rotation, trust roots, least privilege |
| [`orchestration`](domains/orchestration/domain.md) | Control plane vs data plane, scheduling, drift, idempotence, immutable vs mutable, bootstrap dependencies |
| [`observability`](domains/observability/domain.md) | Metrics/logs/traces, cardinality discipline, alerting, SLOs, health models and probes |
| [`capacity`](domains/capacity/domain.md) | Capacity envelopes, headroom, queueing, backpressure, resource topology, locality |
| [`reliability`](domains/reliability/domain.md) | Redundancy, failure domains, quorum, retries, timeouts, circuit breaking, graceful degradation |
| [`security`](domains/security/domain.md) | Trust boundaries, proxy/forwarded identity, fail-open vs fail-closed, resource isolation, noisy neighbors |

Flows call domains for analysis and actions; **flows own the transitions**. A
networking specialist knows how to modify routing; it does not independently
decide whether routing is safe to modify.

## Primitives (recurring state concepts)

`topology`, `dependency-graph`, `failure-domain`, `blast-radius`,
`state-ownership`, `invariants`, `health-model`, `rollback`, `evidence` —
see `primitives/`. Flows compose these rather than each embedding its own
mental model.

## Policies (hard gates)

`mutation-gates`, `production-safety`, `destructive-change`, `concurrency`,
`evidence-thresholds` — see `policies/`. Policies bind all flows; no flow may
weaken them.

## Composition with other StateWorks

Infrae determines whether the infrastructure change itself is sound; Gitter
governs repository/history state; Getter governs how the resulting change is
reviewed and landed. None calls another — handoff packets route through the
operator or the FrameWorks dispatcher.

---

## Standard Review Output

```text
State: YELLOW

Invariant
- Requests must continue through loss of one worker.

Current topology
- 3 workers across 2 hosts.

Finding
- Two workers share Host A.
- Loss of Host A leaves only one worker.
- Surviving worker lacks validated capacity for full traffic.

Blocking
- Failure-domain redundancy is weaker than replica count implies.
- Post-failure capacity has not been validated.

Non-blocking
- Dashboard naming cleanup.

Required evidence
- Host-loss test.
- Capacity test on surviving topology.

Next
- Rebalance one worker to a third failure domain and rerun failure-capacity validation.
```

## Architecture Review Questions

Challenge infrastructure with questions such as:

```text
What happens if this host dies?
What happens if this database is slow rather than dead?
What happens if DNS is stale?
What happens if half the nodes receive the new config?
What happens if credentials rotate during an active request?
What happens when traffic doubles? When retries begin? When storage fills?
What happens if the control plane disappears?
What happens if rollback must occur after state has changed?
What is the actual source of truth?
Where is the irreducible single point of failure?
What evidence proves recovery?
```

## Anti-Patterns

Infrae rejects: "works on my machine" as production evidence; green
dashboards as proof; health = liveness; replicas treated as resilience
without failure-domain analysis; replication treated as backup; backup
treated as recovery without restore testing; rollouts without rollback or
forward-recovery reasoning; uncontrolled retries; missing timeouts; restarts
as root-cause fixes; resource totals treated as unified capacity; capacity
planning without failure headroom; network location as sufficient identity;
secrets in config or logs; manual production mutation without recording
resulting state; IaC as proof of effective runtime state; dashboard count as
observability; scaling before identifying the bottleneck; infrastructure
complexity without a concrete requirement; microservice decomposition without
real independent boundaries; central infrastructure God Objects (a
distributed God Object is still a God Object); hidden shared state or
credentials; uncontrolled concurrent infrastructure agents; migration plans
assuming atomic cutover; destructive operations without recovery evidence;
root cause declared from temporal correlation; high availability claimed
without testing meaningful failures; production readiness claimed without a
declared operating envelope.

## Final Principles

> Design for failure, not merely deployment.
> Observe effective state, not only declared state.
> Redundancy is meaningless without failure-domain independence.
> Capacity without headroom is borrowed availability.
> Backup without restore evidence is hope.
> Monitoring without actionable interpretation is decoration.
> A successful command proves only that the command succeeded.
> Infrastructure complexity must pay rent.
> Every production change is a hypothesis until the running system verifies it.
> Unknown risk should be made explicit, not silently converted into confidence.
