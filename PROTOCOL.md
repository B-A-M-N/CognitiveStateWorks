# CognitiveStateWorks — StateWork Protocol

CognitiveStateWorks governs **domain state**: what state a domain is in, which
transitions are legal, what evidence permits a transition, what invalidates
the state, and how to recover. It does not govern general reasoning — that is
CognitiveFrameWorks' job, and it sits beneath StateWorks as shared reasoning
policy.

```text
CognitiveFrameWorks    → "How should I think?"
CognitiveStateWorks    → "What state am I in? What transitions are legal?"
Domain StateWorks      → Infrae, Gitter, Getter, ... — protocol instantiations
```

This document defines the protocol for **building** a StateWork. It is
deliberately not a giant prompt containing every state machine — each domain
implements the protocol for itself.

---

## The Protocol

Every StateWork defines:

### 1. Domain
What real-world state this StateWork owns, and what it explicitly does not
own. A StateWork that owns everything owns nothing.

### 2. State vocabulary
The named states the domain can be in. States must be mutually distinguishable
by observation, not by mood. Keep the vocabulary small enough to hold in
working memory.

### 3. State observations
What must be observed to know which state the domain is actually in — and the
standing rule that **declared state and effective state may disagree**, and
that disagreement is itself a finding. Observation must not mutate the thing
observed.

### 4. Invariants
What must remain true across any legal transition. Work without an identified
invariant is churn.

### 5. Allowed transitions
The legal edges of the state graph. Anything not listed is illegal by
default, no matter how convenient.

### 6. Transition guards
The conditions that must hold before a transition may fire. Guards are
answered by evidence, not by optimism.

### 7. Evidence requirements
What observation proves — and at what strength — for each guarded transition.
A successful command is construction evidence, not correctness evidence.

### 8. Mutation authority
Who (human, agent, flow) may fire which transitions, and what ownership must
be established first. Unknown ownership means additive or isolated action
only.

### 9. Invalidation rules
What reopens the state: operator observations, contradictory evidence,
environment drift, concurrent mutation. A model built five minutes ago may
already be wrong.

### 10. Failure states
The named states representing things gone wrong (degraded, blocked, incident,
partial). Failure states are first-class, not exceptional prose.

### 11. Recovery transitions
How failure states return to good ones, and what evidence proves recovery is
complete — which is never merely "the command succeeded again."

### 12. Completion states
The terminal states and the explicit checklist each requires. Completion is
defined by verified conditions, not by task exhaustion.

### 13. Handoff contracts
The structured packet one StateWork or flow hands to another, so composition
happens through explicit artifacts rather than shared memory.

---

## Don't mix three different concepts

StateWork protocol distinguishes three kinds of vocabulary, and a StateWork
must never flatten them into one enum:

| Concept | Example | Meaning |
|---------|---------|---------|
| Transition state | `PLANNED`, `CHANGING`, `STABLE` | Determines which actions are legal |
| Readiness / classification | `RED`, `YELLOW`, `GREEN` | Describes the system's condition |
| Risk / severity | `LOW`, `HIGH`, `CRITICAL` | Input to transition guards |

The stale Getter statement this protocol previously carried — claiming Getter
used the color readiness vocabulary — demonstrates exactly why the distinction
matters. Getter classes risk; Infrae overlays readiness; neither is a
transition state.

## Authoring vs. runtime

This file is the full authoring specification. Active models carry only the
runtime kernel in `RUNTIME.md`. Dispatchers route by manifest —
`schemas/statework-manifest.schema.json` and each StateWork's `manifest.yaml` —
never by this prose.

## Current instantiations

| StateWork | Domain | Location |
|---|---|---|
| **Infrae** | Infrastructure state | `infrae/` |
| **tui'd** | Terminal user interface state | `tuid/` |
| **Gitter** | Repository observation state | `gitter/` |
| **Getter** | Repository mutation state | `getter/` |
| *future* | Deployment, security incident, data migration, release, PR lifecycle | — |

Gitter's Truth Packet and Getter's Evidence Packet are handoff contracts
(element 13). Getter's risk classes are `LOW / MODERATE / HIGH / CRITICAL`
(risk/severity vocabulary, not transition states). The color readiness
overlay (`RED / ORANGE / YELLOW / GREEN / BLUE`) belongs to Infrae's readiness
classification and is not part of Getter's vocabulary.

## Composition rule

StateWorks never call each other. A flow inside one StateWork produces a
handoff packet; the composition layer (the operator, or CognitiveFrameWorks'
dispatcher) routes it. This is the anti-God-Object boundary: shared reasoning
lives in FrameWorks, state machines live in StateWorks, and neither absorbs
the other.
