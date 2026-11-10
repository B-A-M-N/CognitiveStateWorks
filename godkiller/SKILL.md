---
name: godkiller
description: >
  Technology-agnostic CognitiveStateWorks skill for diagnosing God Objects and responsibility concentration, identifying legitimate ownership boundaries, performing authorized incremental decomposition, detecting fake decomposition, preserving behavior, and independently verifying the separated system. Can conclude no decomposition is justified. Never requires TerraFormer.
---

# GodKiller — Architectural Decomposition StateWork

**Mission:** determine whether architectural authority is excessively concentrated, establish genuinely independent responsibilities, and verify safe separation. Works on functions, classes, modules, packages, services, pipelines, plugins, workflow engines, agents, and data/process boundaries. **Independently complete.** It does not require or call TerraFormer, dictate architecture style, or own product design/deployment.

## Start here

1. Establish the **actual observed subject and revision**; distinguish declared architecture from runtime behavior. Inspect source, runtime interactions, ownership, side effects, state transitions, public consumers, and change history as appropriate. Record unknowns.
2. Establish **behavioral baselines and oracles** before modifying code/configuration. Include operational, security, concurrency, lifecycle, error, and compatibility behavior where relevant.
3. Diagnose excess concentration with causal evidence; large code size alone is never dispositive. Identify boundaries by responsibility and exclusive or explicitly coordinated mutable authority.
4. Generate multiple plausible partitions including **no decomposition**. Reject partitions that merely relocate methods while preserving undisciplined shared state, central dispatch, or a circular dependency knot.
5. Plan **smallest reversible extraction**: owner, responsibility, exposed contract, dependents, old/new state access, sequencing, migration method, compatibility shim, rollback, measurable invariant.
6. Before each edit, seek authorized mutation through the host/operator. Unclear ownership means observe, document, or isolate—do not mutate consequential state.
7. Extract one boundary at a time. Independently verify behavior, ownership, API compatibility, cycles, runtime/lifecycle constraints, and rollback. Update the Architecture Boundary Packet (ABP); repeat incrementally.
8. Produce evidence-backed completion or explicit blocked/partial status. Never report success solely from compilation, number of files, mocks, or unit tests of isolated classes.

## State and authority

`UNASSESSED → MAPPED → DIAGNOSED → PARTITIONED → EXTRACTING → VERIFIED → HANDOFF_READY`.

`NO_DECOMPOSITION_NEEDED` is a **successful negative diagnosis**, not a failure. `BLOCKED`, `INVALIDATED`, and `RECOVERY_REQUIRED` are first-class exceptional states. Only transitions in `transitions.yaml` are legal; a declared state is not automatically the effective state. Host-attested evidence and subject-revision CAS govern progress. If advisory-only, these are instructions, **not independently enforced transitions**.

**Important:** GodKiller is the *workflow-state and evidence authority for decomposition claims*, not an unconstrained code-mutation authority. The host/operator authorizes modifications. CSW keeps durable workflow state. Reasoning frameworks and behavioral guidance are optional, never dependencies.

## CognitiveStateWorks and CognitiveFrameWorks fit

This bundle is registered as the `godkiller` CSW workflow. CSW selects it only when its manifest and flow predicates match; the trusted host remains responsible for invoking the workflow authority, recording trusted evidence, and accepting legal transitions. This guidance cannot itself persist state or make a transition legal. An advisory installation supplies instructions only.

GodKiller owns the architectural decomposition assessment and its `godkiller_boundary_packet`. It does not replace adjacent StateWorks: use Gitter's repository truth when repository ownership, revision, or dirty state is relevant; use Getter for Git history or branch mutations; and use Infrae when infrastructure state or infrastructure operations are the subject. Their packets remain independently owned. Route between StateWorks through the CSW host and declared packets, not an implicit skill-to-skill call.

When CognitiveFrameWorks is present, its components are optional behavioral support: OWL checks diagnosis and partition reasoning; ANCHOR preserves revision-bound findings and recovery state; DOX checks repository instruction contracts; FUSE selects evidence-gathering and verification actions; FLOW challenges needless complexity; SISPIS calibrates the report. WARD and the trusted host's own action gate constrain consequential changes. These components do not grant mutation permission, alter CSW evidence, or override CSW transitions. Without CFW, follow the same evidence, authorization, and transition requirements directly.

## Default proofs before `VERIFIED`

- The extracted responsibility has a named decision and state owner and a narrow, explicit contract.
- The original owner no longer mutates extracted state except through the declared contract; no hidden 'manager' proxy restores the central bottleneck.
- There are no unexplained bidirectional dependencies, duplicated authoritative state, or accidental ownership races.
- Characterization/contract and regression checks cover the original public behavior, errors, cancellation, lifecycle, concurrency and compatibility appropriate to the change.
- The implementation, tests, and evidence refer to the **same subject revision**.
- The current slice can be reverted or recovered without making state corruption worse.

## Outputs

Emit `godkiller_boundary_packet` under CSW's canonical handoff envelope; its `payload.architecture_boundary` follows `architecture-boundary/v1`. The same architecture facts can be handed to any consumer. Write the assessment, boundary decision, slice plan, evidence ledger and honest residual risks. A **negative decision** returns `NO_DECOMPOSITION_NEEDED` with rationale and evidence. Partial extraction remains `EXTRACTING`/recovery until verified.

## Route by need

- `flows/triage`: safe default for ambiguous, unfamiliar subjects.
- `flows/map`, `flows/diagnose`, `flows/partition`: observational boundaries and planning.
- `flows/extract`, `flows/verify`, `flows/handoff`: controlled extraction, independent proof, self-contained handoff.
- `flows/recover`: invalidation, rollback and re-observation.

See `references/diagnosis.md`, `references/boundaries.md`, `references/extraction.md`, `references/verification.md`, `references/authority.md`, `contracts/architecture-boundary.md`, `templates/`, and `qualification/`.

## Stop rules

Stop consequential mutation when owner unknown, baseline absent, revision changed, operator observation contradicts the model, change lacks rollback, severity-critical invariant is untestable, or a proposed boundary is only cosmetic. Record a BLOCKED/INVALIDATED/RECOVERY_REQUIRED state as appropriate. If decomposition is not justified, say so and stop—do not generate abstraction for its own sake.
