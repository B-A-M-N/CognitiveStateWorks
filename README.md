# CognitiveStateWork

> **State-aware workflow control for AI agents.**
> Encode what state the work is actually in, what transitions are legal next, and what evidence is required before the agent can move forward.

CognitiveStateWork (CSW) is the **operational state layer** of a larger closed-loop architecture for reliable AI agents.

It emerged from a problem that behavioral instructions alone could not solve. CognitiveFrameWorks improved how agents reasoned, verified, recovered, and acted, but agents could still mutate a repository before establishing its state, treat deployment as proof of infrastructure health, declare a UI fixed without exercising the defect, or jump from activity directly to completion.

Those were not merely behavioral failures. They were **state-model failures**. The agent needed to know not just how to behave, but:

> **What state is this work actually in, and what behavior is valid from here?**

CSW exists to answer that question.

## The larger architecture

| System | Primary question |
| --- | --- |
| **CognitiveFrameWorks** | **How should the agent behave?** |
| **CognitiveStateWork** | **What behavior and transitions are appropriate now?** |
| **Digital Psychology** | **Why is the agent behaving this way under these conditions?** |

```text
             CognitiveFrameWorks
             behavioral policy
                    │
                    ▼
Task ───────→ effective runtime policy
                    │
                    ▼
             CognitiveStateWork
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
                    └─────────────→ Digital Psychology
                                      behavioral analysis
```

CFW provides general behavioral discipline. CSW provides **domain-specific operational structure**. Digital Psychology measures whether either system actually improves behavior.

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

CSW owns **durable operational state**. CFW owns the **runtime execution session**. Digital Psychology uses session/attempt identity to reconstruct behavior without corrupting the domain state model.

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

CognitiveStateWork
    decides what domain state exists
    and which transitions are legal
```

For example, CFW/FUSE may require verification to exercise the changed infrastructure boundary; Infrae declares the evidence required for `CHANGING → VERIFIED`. CFW/WARD may require authority for a mutation; Infrae declares that `PLANNED → CHANGING` is not legal until its transition requirements are met.

Digital Psychology observes agents traversing StateWorks and can ask whether they skip `MODELED`, create unnecessary recovery loops, misuse specialists, declare completion immediately after `VERIFIED`, or incur more correction cycles in one flow than another.

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

## The role of CognitiveStateWork

```text
CognitiveFrameWorks
    HOW should the agent behave?

CognitiveStateWork
    WHAT behavior and transitions are appropriate NOW?

Digital Psychology
    WHY does this behavior recur under THESE CONDITIONS?
```

CFW made recurring behavioral errors governable. CognitiveStateWork extends that idea to recurring **workflow errors** by making operational state explicit. Together with Digital Psychology, those state models become observable and testable rather than static instructions.
