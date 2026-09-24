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

- `StandaloneHostInterface` for resolving StateWorks, starting or resuming subjects, submitting attested observations, requesting transitions, and recovering from invalidation.
- `SubjectStateStore` for durable state keyed by namespace, application, subject, StateWork, and contract version.
- Revision compare-and-swap updates and append-only transition history so stale writers re-inspect instead of overwriting newer state.
- `EvidenceStore` for trusted evidence references, attestation integrity, persistence, and restart recovery.
- Explicit consequential transition markers and registered provenance for authorization, mutation, verification, and terminal-state transitions.
- Flow-selection metadata, transition contracts, packet schemas, evidence-kind registry, and repository-truth validation in the enforcing product.

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

The example uses the Gitter transition contract, initializes a subject through `StandaloneHostInterface`, rejects a transition without trusted evidence, accepts a repository-truth reference, and proves that state survives a new interface instance.

For a deployable enforcing installation:

```bash
python3 scripts/install-stateworks.py \
  --registry demo="$HOME/.demo-csw" \
  --enforcing-runtime
```

That product contains the controller, schemas, transition contracts, evidence registry, StateWorks, flows, and repository-truth validator. The ordinary installation remains an advisory skill product.

## Optional integrations

- **CSW alone:** use `StandaloneHostInterface` and the enforcing installation; CFW and DP are not required.
- **CSW + CFW:** CFW may compose StateWork flow eligibility and framework enhancements, but CSW retains state and evidence authority.
- **CSW + DP:** DP may recommend a legal future flow preference. It cannot create flow eligibility, weaken a transition contract, or rewrite an active subject state.

The top-level architecture diagram is a combined deployment view, not a statement that CFW is required for CSW execution. The standalone quickstart above is the canonical CSW entry point.

## The larger architecture

| System | Primary question |
| --- | --- |
| **CognitiveFrameWorks** | **How should the agent behave?** |
| **CognitiveStateWorks** | **What behavior and transitions are appropriate now?** |
| **DigitalPsychology** | **Why is the agent behaving this way under these conditions?** |

```text
             CognitiveFrameWorks
             behavioral policy
                    │
                    ▼
Task ───────→ effective runtime policy
                    │
                    ▼
             CognitiveStateWorks
             operational state
                    │
             legal transitions
                    │
                    ▼
                  Agent
                    │
            real actions/results
                    │
                    ▼
             state observations
                    │
                    └─────────────→ DigitalPsychology
                                      behavioral analysis
```

CFW provides general behavioral discipline. CSW provides **domain-specific operational structure**. DigitalPsychology measures whether either system actually improves behavior.

## A StateWork is an executable workflow model

A StateWork is not simply a skill describing best practices. It defines a domain as explicit operational state and can specify:

* states, vocabulary, and initial state;
* legal transitions, normal paths, and failure/recovery paths;
* triggers, evidence requirements, invalidation rules, and completion states;
* typed inputs, outputs, handoff packets, flows, and specialists;
* framework requirements and runtime metadata.

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
          ├── domain/triggers
          ├── phase and inputs/outputs
          ├── framework requirements
          ├── flows
          └── runtime metadata
```

Registration means **this StateWork is available to the resolver**. It does not mean **load this StateWork into every agent**. CognitiveFrameWorks resolves the task, selects the applicable StateWork chain, and activates only what is needed.

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

CSW owns **durable operational state**. CFW owns the **runtime execution session**. DigitalPsychology uses session/attempt identity to reconstruct behavior without corrupting the domain state model.

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

Validation checks registry integrity, manifest and transition schemas, unique identities, packet registration, producer/consumer consistency, declared states, legal paths, completion reachability, failure/recovery routes, framework requirements, and typed handoff fixtures.

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

CSW is a domain-state runtime, not a general database or policy language. Trusted hosts must provide evidence validators and deployment-specific freshness context. The automated three-project release gate is in the sibling CFW repository; real-agent reasoning claims require CFW's external-agent qualification harness.

## License and contribution

These projects are released under the [MIT License](LICENSE). Contributions are welcome through repository issues and pull requests. Please include a focused regression or acceptance check for behavior changes, keep authority boundaries explicit, and do not claim model-performance improvements without the corresponding qualification evidence.

## FreeInference attribution
This work benefited in some way from inference provided by [freeinference.org](https://freeinference.org/).

These are independent developments that are not reviewed, endorsed, or sponsored by FreeInference. If you find these projects genuinely useful, please consider donating to or sponsoring FreeInference, which provides a vital inference service.
