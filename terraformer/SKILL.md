---
name: terraformer
description: >
  Technology-agnostic CognitiveStateWorks skill for independently recomposing existing or newly separated components: discover actual contracts, resolve ownership conflicts, connect components through explicit interfaces, compose initialization/cancellation/teardown/recovery, preserve external compatibility, and qualify integrated behavior end-to-end. Does not require GodKiller.
---

# TerraFormer — Architectural Recomposition StateWork

**Mission:** turn independently owned components into one coherent operational system while **preserving** their boundaries. Works on services, modules, libraries, plugins, event systems, agent harnesses, pipelines, and shared-state/concurrent systems. **Independently complete.** Components may come from existing designs, humans, automation, GodKiller, or other sources; no upstream skill is required.

## Start here

1. Observe the *actual* components, versions, contracts, authority, configuration, lifecycles, and runtime capabilities—not merely their presence in files. Establish the subject revision and verify provenance of any supplied architecture packet.
2. Enumerate required user/system journeys end-to-end. Identify which component owns each mutable resource, decision, error, cancellation, and observable result. Detect contract mismatches, partial availability, hidden coordination, and boundary crossing.
3. Reconcile protocols: names, types, schemas, versions, compatibility, sync/async assumptions, ordering, concurrency, idempotency, retries, timeouts, backpressure, events, failure semantics, trust boundaries, and state-sharing rules where applicable.
4. Decide if composition is required. If already coherent and qualified, choose **NO_COMPOSITION_NEEDED**. If fundamental conflicts are unresolved, choose `INCOMPATIBLE` rather than fabricate an interface.
5. Plan the smallest reversible connection slice, with an owner for each edge. Specify adapter/ports only where demonstrated necessary, initialization order, lifecycle and resource release, rollback, required public compatibility, and observable proof.
6. Obtain authorization and connect components without a central controller that accumulates other components' decisions or state. Prefer direct contracts/ports; do not impose an event bus, DI, microservices, RPC, or orchestration framework without evidence.
7. Exercise complete paths from external entry through outputs and back, including error, cancellation, retry, startup/shutdown, recovery, concurrency, and cross-component state synchronization as applicable. Isolated unit tests are **not integration qualification**.
8. Publish `terraformer_integration_packet` with independently observed evidence and unresolved issues. For phased integration, qualify each slice and proceed; never convert 'some wiring exists' to `COMPLETE`.

## State and authority

`UNASSESSED → CONTRACTS_VALIDATED → COMPOSITION_PLANNED → CONNECTING → INTEGRATED → QUALIFIED → COMPLETE`.

`NO_COMPOSITION_NEEDED` is a legitimate evidence-backed terminal conclusion. `INCOMPATIBLE`, `PARTIALLY_INTEGRATED`, `BLOCKED`, `INVALIDATED`, and `RECOVERY_REQUIRED` are first-class. The contract in `transitions.yaml` is authoritative for legal state edges. Host-attested, revision-bound evidence and host/operator mutation authorization are required. Advisory-only installation **does not** independently enforce transitions.

**TerraFormer owns integration workflow state and evidence, not runtime scheduling, deployment, architectural omniscience, or other components' domain state.** CFW/DP may enhance reasoning but are never required for core correctness.

## CognitiveStateWorks and CognitiveFrameWorks fit

This bundle is registered as the `terraformer` CSW workflow. CSW selects it only when its manifest and flow predicates match; the trusted host remains responsible for invoking the workflow authority, recording trusted evidence, and accepting legal transitions. This guidance cannot itself persist state or make a transition legal. An advisory installation supplies instructions only.

TerraFormer owns the integration assessment and its `terraformer_integration_packet`. It does not replace adjacent StateWorks: use Gitter's repository truth when repository ownership, revision, or dirty state is relevant; use Getter for Git history or branch mutations; and use Infrae when infrastructure state or infrastructure operations are the subject. Their packets remain independently owned. Route between StateWorks through the CSW host and declared packets, not an implicit skill-to-skill call. A GodKiller boundary packet may be consumed as untrusted input after provenance and revision checks; it is never a TerraFormer prerequisite.

When CognitiveFrameWorks is present, its components are optional behavioral support: OWL checks contract reconciliation and composition decisions; ANCHOR preserves revision-bound findings and partial-integration recovery state; DOX checks repository instruction contracts; FUSE selects end-to-end evidence and qualification actions; FLOW challenges unnecessary adapters and coordination overhead; SISPIS calibrates the closeout. WARD and the trusted host's own action gate constrain consequential changes. These components do not grant mutation permission, alter CSW evidence, or override CSW transitions. Without CFW, follow the same evidence, authorization, and transition requirements directly.

## Default proofs before `QUALIFIED`

- All required components exist and their effective versions and interfaces match the recorded claims.
- A full user/system path crosses every necessary interface with observable correlated results; not just constructed links.
- Ownership is unambiguous; shared authority uses a concrete coordination/consistency protocol with failure semantics. No compensating 'integration manager' silently becomes the original God Object.
- Startup ordering, readiness, execution, cancellation, teardown, failure and recovery are tested where relevant.
- Cross-component concurrency, retries, idempotency and consistency are exercised rather than inferred from unit tests.
- Public compatibility and old consumer behavior are preserved or explicitly approved as intentional changes.
- Integration evidence names the exact subject revision and does not conflate passing local tests with system-wide verification.

## Outputs

Emit `terraformer_integration_packet` under the canonical CSW envelope, with `payload.architecture_boundary` conforming to `architecture-boundary/v1`. An upstream `godkiller_boundary_packet` is optional **data**, never required or trusted automatically. Partial integration must have explicit owner, scope, consumer-visible impact, and resumable rollback path.

## Route by need

- `flows/triage` for ambiguous/unknown systems, `flows/inventory` and `flows/reconcile` for discovery and contract mismatch.
- `flows/plan`, `flows/connect` for authorized incremental composition.
- `flows/qualify`, `flows/complete` for real-system evidence and closeout.
- `flows/recover` for incompatibility, partial integration, invalidation, and rollback.

See `references/reconciliation.md`, `references/ownership.md`, `references/lifecycle.md`, `references/qualification.md`, `references/authority.md`, `contracts/architecture-boundary.md`, `templates/`, and `qualification/`.

## Stop rules

Stop consequential mutation when one or more components are unavailable or unverified, authority conflicts unresolved, interface compatibility unknown, observed revision stale, external behavior lacks a baseline, rollback absent, or a failed end-to-end check is being disguised as partial success. Use `INCOMPATIBLE`, `PARTIALLY_INTEGRATED`, or `BLOCKED` as appropriate. Complete only the declared scoped slice, not unrelated future integration.
