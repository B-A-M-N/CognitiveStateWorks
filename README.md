# CognitiveStateWorks

> **State-aware workflow control for AI agents.**
> Encode what state the work is actually in, what transitions are legal next, and what evidence is required before the agent can move forward.

CognitiveStateWorks (CSW) is the **operational state layer** of a larger closed-loop architecture for reliable AI agents.

It emerged from a problem that behavioral instructions alone could not solve. CognitiveFrameWorks improved how agents reasoned, verified, recovered, and acted, but agents could still mutate a repository before establishing its state, treat deployment as proof of infrastructure health, declare a UI fixed without exercising the defect, or jump from activity directly to completion.

Those were not merely behavioral failures. They were **state-model failures**. The agent needed to know not just how to behave, but:

> **What state is this work actually in, and what behavior is valid from here?**

CSW exists to answer that question.

## Current implementation

CognitiveStateWorks provides both an advisory installation and an enforcing standalone installation.

The enforcing runtime includes:

- `WorkflowAuthority` with a shared, engine-neutral step API for state-machine and milestone/checklist workflows.
- `StandaloneHostInterface` for resolving StateWorks, starting or resuming subjects, submitting attested observations, requesting workflow steps, and recovering from invalidation.
- `SubjectStateStore` for durable state keyed by namespace, application, subject, StateWork, and contract version.
- Revision compare-and-swap updates and append-only transition history so stale writers re-inspect instead of overwriting newer state.
- `EvidenceStore` for trusted evidence references, attestation integrity, persistence, and restart recovery.
- Explicit consequential transition markers and registered provenance for authorization, mutation, verification, and terminal-state transitions.
- A compiled bundle registry with local packet/evidence contracts, freshness rules, and trusted engine pins.
- Bounded, data-only flow predicates with explicit fallback, ambiguity, and no-match policy.
- Runtime capsules generated from the compiled manifest and workflow contract, with optional `guidance.md` text.

The control-plane module remains a compatibility facade for existing imports. Its resource loaders live in `scripts/resources.py`, trusted evidence validators, freshness evaluation, and attested storage live in `scripts/evidence.py`, and shared exceptions live in `scripts/errors.py`.

The Python wheel includes the core, schemas, and the built-in Gitter, Getter, TUID, and Infrae bundles. Install it and compile its packaged built-ins with:

```bash
python3 -m pip install .
cognitive-statework-compile-registry
```

The compiler writes the immutable registry beside the packaged built-ins. Trusted data-only bundles can then be added through a host-owned registry configuration.

External executable extensions use the `cognitive_statework.engines`, `cognitive_statework.evidence_validators`, and `cognitive_statework.freshness_validators` entry-point groups. A host must explicitly adopt each distribution/version/entry-point identity and pin its distribution Python-source SHA-256 through the corresponding registry's `load_trusted_entry_points(...)` method. The pin is checked before loading; compiled registries also pin the adopted implementation hashes. Data-only bundles cannot trigger Python imports.

Use the advisory product for documentation and workflow guidance:

```bash
python3 scripts/install-stateworks.py --registry example-host="$HOME/.example/skills"
```

Use the enforcing product for standalone state authority:

```bash
python3 scripts/install-stateworks.py \
  --registry example-host="$HOME/.example/skills" \
  --enforcing-runtime
```

The `validate-stateworks.py`, `test-control-plane.py`, and `test-concurrent-state.py` suites cover registration integrity, transition legality, provenance, restart recovery, and concurrent state safety.

## Five-minute standalone quick start

CSW can own state and evidence without CFW or DP. From this repository, run the enforcing runtime example:

```bash
python3 scripts/quickstart-standalone.py
```

Expected output:

```text
initial: UNKNOWN revision 1
transition without evidence allowed: False
transition with trusted evidence allowed: True
after restart: OBSERVED revision 2
```

The example uses the Infrae transition contract, initializes a subject through `StandaloneHostInterface`, rejects a transition without host-attested discovery evidence, and proves that state survives a new interface instance. Repository-truth transitions remain bound to their specialized validator.

For a deployable enforcing installation:

```bash
python3 scripts/install-stateworks.py \
  --registry demo="$HOME/.demo-csw" \
  --enforcing-runtime
```

That product contains the controller, schemas, compiled StateWork bundles, flows, and validators declared by the runtime package. The ordinary installation remains an advisory skill product.

## Optional integrations

- **CSW alone:** use `StandaloneHostInterface` and the enforcing installation; CFW and DP are not required.
- **CSW + CFW:** CFW supplies task components and action enforcement; CSW retains workflow selection, state, evidence, and transition authority.
- **CSW + DP:** DP may rank and request activation of an eligible StateWork. CSW checks the composition and selection revision, then records the active set; DP cannot create eligibility, weaken a transition contract, or rewrite workflow state.
- **CSW + CFW + DP:** CFW supplies cognitive components and action enforcement, DP coordinates behavior through explicit ports, and CSW remains the authority for workflow selection, state, evidence, and legal transitions.

| Deployment | CSW role | Other-system requirement |
| --- | --- | --- |
| **CSW alone** | Workflow selection, durable subject state, evidence, and legal transitions | None |
| **CFW alone** | Not loaded | CFW resolves components and action enforcement independently |
| **CSW + DP** | Authoritative workflow state, eligibility, evidence, and transition enforcement | DP may request an eligible StateWork through the private host control bridge |
| **CFW + DP** | Not loaded | DP can adapt without CSW; CFW independently enforces any separately enabled action gates |
| **CFW + CSW** | Authoritative workflow state and evidence | CFW supplies task components and action guards; DP is not required |
| **CFW + CSW + DP** | Authoritative workflow state, candidate eligibility, and transition enforcement | DP coordinates behavioral interventions; CFW supplies signals and validates component directives |

CSW's standalone runtime and its CFW integration remain usable without DP.
The complete three-system deployment adds adaptation while preserving CSW as
the only authority that can activate eligible StateWorks or commit legal
workflow transitions.

CFW discovers this integration through the optional
`cognitiveframeworks.statework_providers` Python entry point included in the
CSW package. Installing CSW does not require CFW; CFW-only deployments use an
empty provider and do not import CSW.

The host calls `WorkflowAuthority.behavioral_snapshot(...)` with the workflow
scope and an optional bounded candidate list. It does not supply active
workflow identities: CSW reads those from its own revisioned selection store.
The snapshot returns current authoritative workflow states and legal steps,
plus only registered, composition-compatible StateWorks with bounded
`behavior_tags`. DP may rank those candidates; tags are descriptive hints and
do not grant activation or transition authority. Activation uses
`WorkflowAuthority.activate_workflow(...)` with a contract hash and expected
selection revision. Independent host activations are permanent unless the host
explicitly releases them. A DP activation must include its control-session and
intervention IDs plus an action-index expiry; only that matching DP owner can
release it. CSW expires due DP leases during a behavioral snapshot when the
host supplies the current action index, while preserving composition-required
dependencies and independently owned selections. Applying any workflow step still uses
`WorkflowAuthority.apply_step(...)` with evidence and an expected workflow
revision.

In the three-system runtime, DP receives a CSW snapshot containing the current
selection revision, active workflow states, legal steps, and only registered,
composition-compatible candidates. DP may request one eligible activation or
release a temporary selection when its bounded intervention ends. CSW checks
the expected selection revision for either operation and returns the new
authoritative snapshot. DP cannot infer eligibility from tags or claim that a
requested StateWork became active without CSW confirmation.

The top-level architecture diagram is a combined deployment view, not a statement that CFW is required for CSW execution. The standalone quickstart above is the canonical CSW entry point.

The three-system host sends sequenced task, action, workflow, validator, and
completion observations to DP. DP requests bounded StateWork lease changes
through CSW's revision-checked API; CSW owns whether each activation or release
is legal. CFW and CSW can also run together without DP, and either remains
independently usable when the other systems are absent.

## The larger architecture

| System | Primary question |
| --- | --- |
| **CognitiveFrameWorks** | **Which cognitive components and enforcement rules are available?** |
| **CognitiveStateWorks** | **Which workflow state and transitions are legal now?** |
| **DigitalPsychology** | **How should behavior adapt, and did the intervention improve progress?** |

```text
                    DigitalPsychology runtime host
                 observes and selects a bounded intervention
                          ↙                       ↘
          CFW signals and directives       CSW state and eligible choices
          CFW validates controls           CSW validates workflow operations
                          ↘                       ↙
                                     Agent
                                       │
                        actions, artifacts, host evidence
                                       │
                                       ▼
                      independent DP outcome evaluator
                                       │
                  retain, relax, reverse, or refine policy
```

CFW provides cognitive components and action enforcement. CSW provides **authoritative domain workflow state**. DigitalPsychology owns cross-system behavioral adaptation and measures progress against the user's objective.

The diagram shows the full adaptive deployment. CSW remains usable alone, and
CFW+CSW can run together without DP. When DP is enabled, its outcome evaluator
uses host and CSW evidence to assess whether a targeted intervention improved
required-goal progress; the controlled agent's completion statement is not the
success signal.

## A StateWork is an executable workflow model

A StateWork is a self-describing workflow bundle, not only a state machine or a skill. It defines a domain and can specify:

* a workflow contract for a trusted engine such as `state_machine` or `milestone`;
* legal steps, dependencies, failure/recovery paths, and completion rules;
* triggers, evidence requirements, invalidation rules, and completion states;
* typed inputs, outputs, handoff packets, flows, and specialists;
* bundle-local packet and evidence contracts, namespaced integrations, and optional guidance.

```text
observation
    │
    ▼
CURRENT STATE
    │
    ├── transition not legal ─────→ BLOCK / RECOVER
    │
    └── transition legal
            │
            ├── evidence insufficient ─→ remain in state
            │
            └── evidence sufficient ───→ NEXT STATE
```

This prevents an agent's narrative from becoming the state machine. The agent does not reach `VERIFIED` because it says "verified"; it reaches `VERIFIED` because the transition contract was satisfied.

## Current StateWorks

| StateWork | Domain |
| --- | --- |
| **Infrae** | Infrastructure state, changes, validation, degradation, recovery |
| **tui'd** | Terminal-interface design, implementation, validation, defects, recovery |
| **Gitter** | Repository observation, truth establishment, isolation |
| **Getter** | Repository mutation, recovery, controlled change |

The architecture is intended to support deployment lifecycle, security incidents, data migration, release qualification, pull-request lifecycle, distributed systems, and agent delegation without redesigning the runtime.

## Discovery is not activation

StateWorks use explicit registration:

```text
registry.yaml
    │
    └── manifest.yaml
          ├── domain/triggers/phase_tags
          ├── inputs/outputs and composition
          ├── namespaced integrations
          ├── flows
          ├── packet/evidence contracts
          └── optional guidance.md
```

Registration means **this StateWork is available to CSW's resolver**. It does not mean **load this StateWork into every agent**. DP may rank options from a CSW snapshot; only CSW can activate the composition-compatible selection for its workflow scope.

Create a data-only extension starter with:

```bash
python3 scripts/new_statework.py release-audit \
  --domain software_release \
  --purpose "Qualify software releases using evidence-backed milestones." \
  --engine milestone
```

The command writes a bundle under `extensions/` and supports either `state_machine`
or `milestone` contracts. Put domain instructions in optional `guidance.md`; the
compiled registry generates the compact runtime capsule from machine-owned metadata.
Compile the registry after editing a bundle:

```bash
python3 scripts/compile-registry.py
```

A flow declares its selector as bounded data:

```yaml
when:
  all:
    - field: operation
      in: [deploy, upgrade]
    - field: current_state
      in: [PLANNED, CHANGING]
```

Only host-exposed routing fields are accepted. The manifest `flow_selection`
contract controls fallback (`required`, `optional`, or `forbidden`), ambiguity,
and whether a no-match makes the StateWork inactive or blocks the plan.

A StateWork can contain multiple flows for different operations or starting conditions:

```text
tui'd
├── inspect
├── design
├── implement
├── debug
└── validate
```

The resolver establishes which flows are **statically legal** first. Behavioral learning may prefer among eligible alternatives, but it must not create eligibility for an unmatched flow. Required specialists cannot be removed by routing; optional specialists may be suppressed only after validated evidence shows they add work without improving outcomes.

## Durable state is not session state

```text
domain/subject state
        ≠ runtime session
        ≠ attempt
        ≠ execution segment
```

A repository, deployment, infrastructure resource, interface, or pull request may persist across many agent sessions. Its operational state cannot be blindly scoped to one chat. Conversely, telemetry from independent sessions must not be merged simply because both operated on the same subject.

CSW owns **durable operational state and active workflow selections**. CFW owns task-local action enforcement and component lifecycle. DigitalPsychology owns cross-system behavioral sessions and uses session/attempt identity to assess interventions without changing CSW state directly.

## Handoffs

StateWorks do not call each other ad hoc. They communicate using typed handoff packets:

```text
StateWork A → PacketStore → StateWork B
```

The common envelope and packet registry preserve the producer, consumer, subject identity, packet type, task provenance, evidence, and versioned schema. This keeps composition explicit and prevents one StateWork from reaching silently into another's internals.

## Invalidations and recovery

State is not monotonic. Real systems regress:

```text
VERIFIED → DEGRADED
STABLE   → DEGRADED
CHANGING → DEGRADED
```

Recovery must be modeled explicitly. A new observation can invalidate an earlier conclusion, so the system distinguishes **the agent already checked this** from **the current evidence still supports this state**. That is a core distinction between a StateWork and a checklist.

## Relationship with the other systems

```text
CognitiveFrameWorks
    decides how work should be conducted

CognitiveStateWorks
    decides what domain state exists
    and which transitions are legal
```

For example, CFW/FUSE may require verification to exercise the changed infrastructure boundary; Infrae declares the evidence required for `CHANGING → VERIFIED`. CFW/WARD may require authority for a mutation; Infrae declares that `PLANNED → CHANGING` is not legal until its transition requirements are met.

DigitalPsychology observes agents traversing StateWorks and can ask whether they skip `MODELED`, create unnecessary recovery loops, misuse specialists, declare completion immediately after `VERIFIED`, or incur more correction cycles in one flow than another.

DP may influence future optional composition, but it cannot rewrite StateWork invariants or declare `CHANGING → STABLE` legal because the verification phase is inconvenient.

## Validation

```bash
python3 scripts/validate-stateworks.py
```

Validation checks registry integrity, manifest and workflow schemas, unique identities, packet and evidence declarations, producer/consumer consistency, legal paths, completion reachability, failure/recovery routes, namespaced integration metadata, and typed handoff fixtures.

A StateWork should be treated as executable policy, not descriptive documentation.

## Core principles

**Agent activity is not domain state.** Running a command does not prove the system changed correctly.

**State transitions require evidence.** The model's confidence does not authorize a transition.

**New observations may invalidate old state.** A stale conclusion is not protected by earlier verification.

**Recovery is part of the model.** Degradation and failure are expected operational conditions.

**Domain state persists beyond a session.** The subject is not the chat.

**Registration is cheap; activation is selective.** Large StateWork libraries should not become large agent contexts.

## The role of CognitiveStateWorks

```text
CognitiveFrameWorks
    HOW should the agent behave?

CognitiveStateWorks
    WHAT behavior and transitions are appropriate NOW?

DigitalPsychology
    WHY does this behavior recur under THESE CONDITIONS?
```

CFW made recurring behavioral errors governable. CognitiveStateWorks extends that idea to recurring **workflow errors** by making operational state explicit. Together with DigitalPsychology, those state models become observable and testable rather than static instructions.

## Tests, limitations, and release status

Run the focused standalone checks:

```bash
python3 scripts/validate-stateworks.py
python3 scripts/test-control-plane.py
python3 scripts/test-concurrent-state.py
```

They verify registry integrity, transition legality, evidence provenance, durable state, restart recovery, and concurrent revision safety. The enforcing package is tested by `install-stateworks.py --enforcing-runtime`.

CSW is a domain-state runtime, not a general database or policy language. Trusted hosts must provide evidence validators and deployment-specific freshness context. The automated three-project release gate is in the sibling CFW repository. The current CFW task benchmark does not establish improvement from the full system; that claim requires host-verified baseline, CFW, CFW+CSW, CFW+CSW+DP, and CFW+CSW+DP+Laya cohorts on the same task distribution.

## License and contribution

These projects are released under the [MIT License](LICENSE). Contributions are welcome through repository issues and pull requests. Please include a focused regression or acceptance check for behavior changes, keep authority boundaries explicit, and do not claim model-performance improvements without the corresponding qualification evidence.

## Subject and workflow isolation

A durable subject key now includes namespace, application, application instance, explicit workflow ID, subject reference, StateWork ID, and contract version. Matching local task, session, or interaction IDs are therefore not sufficient to share state.

CFW supplies an agent-private workflow key by default. Two processes may share a subject only through a pinned, authorized workflow membership. Initial-state races reconcile to the already-initialized snapshot; later writes use compare-and-swap revisions and stale writers must re-inspect.

## FreeInference Acknowledgement

This work benefited in some way from inference provided by [freeinference.org](https://freeinference.org/).

These are independent developments that are not reviewed, endorsed, or sponsored by FreeInference. If you find these projects useful, please consider donating to or sponsoring FreeInference, which provides a vital inference service.
