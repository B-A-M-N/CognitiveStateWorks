# Architecture

Persistence, revisions, authority, evidence, and workflow selection for
CognitiveStateWorks.

## The runtime

CSW provides both an advisory installation and an enforcing standalone
installation. The enforcing runtime includes:

- `WorkflowAuthority` with a shared, engine-neutral step API for state-machine and
  milestone/checklist workflows.
- `StandaloneHostInterface` for resolving StateWorks, starting or resuming
  subjects, submitting attested observations, requesting workflow steps, and
  recovering from invalidation.
- `SubjectStateStore` for durable state keyed by namespace, application, subject,
  StateWork, and contract version.
- Revision compare-and-swap updates and append-only transition history so stale
  writers re-inspect instead of overwriting newer state.
- SQLite WAL persistence for subject state, transition history, packets, and
  workflow selections. Existing JSON stores are imported once into adjacent
  `.sqlite3` files; later reads and compare-and-swap writes use SQLite
  transactions.
- `EvidenceStore` for trusted evidence references, attestation integrity,
  persistence, and restart recovery.
- An engine-neutral workflow fact ledger. Completion is derived from required
  facts backed by valid evidence; invalidating a terminal receipt reopens
  completion, and state corrections commit with their revised facts and history.
- Explicit consequential transition markers and registered provenance for
  authorization, mutation, verification, and terminal-state transitions.
- A compiled bundle registry with local packet/evidence contracts, freshness
  rules, and trusted engine pins.
- Bounded, data-only flow predicates with explicit fallback, ambiguity, and
  no-match policy.
- Runtime capsules generated from the compiled manifest and workflow contract,
  with optional `guidance.md` text.

The control-plane module remains a compatibility facade for existing imports. Its
resource loaders live in `scripts/resources.py`, trusted evidence validators,
freshness evaluation, and attested storage live in `scripts/evidence.py`, and
shared exceptions live in `scripts/errors.py`.

## A StateWork is an executable workflow model

A StateWork is a self-describing workflow bundle, not only a state machine or a
skill. It defines a domain and can specify:

* a workflow contract for a trusted engine such as `state_machine` or `milestone`;
* legal steps, dependencies, failure/recovery paths, and completion rules;
* triggers, evidence requirements, invalidation rules, and completion states;
* typed inputs, outputs, handoff packets, flows, and specialists;
* bundle-local packet and evidence contracts, namespaced integrations, and
  optional guidance.

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
            ├── evidence insufficient ──→ remain in state
            │
            └── evidence sufficient ────→ NEXT STATE
```

This prevents an agent's narrative from becoming the state machine. The agent does
not reach `VERIFIED` because it says "verified"; it reaches `VERIFIED` because the
transition contract was satisfied.

## Compiling and registering the bundles

The Python wheel includes the core, schemas, and the built-in Gitter, Getter,
TUID, Infrae, GodKiller, TerraFormer, and TestWorks bundles:

```bash
python3 -m pip install .
cognitive-statework-compile-registry
```

The compiler writes the immutable registry beside the packaged built-ins. Each
`WorkflowAuthority` pins the verified compiled registry for its lifetime; an
explicit `reload_registry(expected_registry_hash=...)` replaces it only after the
requested hash matches. Trusted data-only bundles can then be added through a
host-owned registry configuration.

External executable extensions use the `cognitive_statework.engines`,
`cognitive_statework.evidence_validators`, and
`cognitive_statework.freshness_validators` entry-point groups. A host must
explicitly adopt each distribution/version/entry-point identity and pin its
distribution Python-source SHA-256 through the corresponding registry's
`load_trusted_entry_points(...)` method. The pin is checked before loading;
compiled registries also pin the adopted implementation hashes. Data-only bundles
cannot trigger Python imports.

## Workflow completion is evidence-derived

Completion is not an absorbing status flag. State-machine and milestone inspection
replay required facts against current evidence. If a required terminal fact is
invalidated, the workflow becomes incomplete again; a later correction records
replacement facts and transition history in the same durable update.

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

Registration means **this StateWork is available to CSW's resolver**. It does not
mean **load this StateWork into every agent**. CSW resolves eligibility and
composition compatibility. The trusted host or DP may choose among the returned
legal candidates; CSW validates the request and commits the active selection for
its workflow scope.

Create a data-only extension starter with:

```bash
python3 scripts/new_statework.py release-audit \
  --domain software_release \
  --purpose "Qualify software releases using evidence-backed milestones." \
  --engine milestone
```

The command writes a bundle under `extensions/` and supports either
`state_machine` or `milestone` contracts. Put domain instructions in optional
`guidance.md`; the compiled registry generates the compact runtime capsule from
machine-owned metadata. Compile the registry after editing a bundle:

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
contract controls fallback (`required`, `optional`, or `forbidden`), ambiguity, and
whether a no-match makes the StateWork inactive or blocks the plan.

A StateWork can contain multiple flows for different operations or starting
conditions:

```text
tui'd
├── inspect
├── design
├── implement
├── debug
└── validate
```

The resolver establishes which flows are **statically legal** first. Behavioral
learning may prefer among eligible alternatives, but it must not create eligibility
for an unmatched flow. Required specialists cannot be removed by routing; optional
specialists may be suppressed only after validated evidence shows they add work
without improving outcomes.

## Durable state is not session state

```text
domain/subject state
        ≠ runtime session
        ≠ attempt
        ≠ execution segment
```

A repository, deployment, infrastructure resource, interface, or pull request may
persist across many agent sessions. Its operational state cannot be blindly scoped
to one chat. Conversely, telemetry from independent sessions must not be merged
simply because both operated on the same subject.

CSW owns **durable operational state and active workflow selections**. CFW owns
task-local action enforcement and component lifecycle. DigitalPsychology owns
cross-system behavioral sessions and uses session/attempt identity to assess
interventions without changing CSW state directly.

## Subject and workflow isolation

A durable subject key now includes namespace, application, application instance,
explicit workflow ID, subject reference, StateWork ID, and contract version.
Matching local task, session, or interaction IDs are therefore not sufficient to
share state.

CFW supplies an agent-private workflow key by default. Two processes may share a
subject only through a pinned, authorized workflow membership. Initial-state races
reconcile to the already-initialized snapshot; later writes use compare-and-swap
revisions and stale writers must re-inspect.

## Handoffs

StateWorks do not call each other ad hoc. They communicate using typed handoff
packets:

```text
StateWork A → PacketStore → StateWork B
```

The common envelope and packet registry preserve the producer, consumer, subject
identity, packet type, task provenance, evidence, and versioned schema. This keeps
composition explicit and prevents one StateWork from reaching silently into
another's internals.

## Invalidations and recovery

State is not monotonic. Real systems regress:

```text
VERIFIED → DEGRADED
STABLE   → DEGRADED
CHANGING → DEGRADED
```

Recovery must be modeled explicitly. A new observation can invalidate an earlier
conclusion, so the system distinguishes **the agent already checked this** from
**the current evidence still supports this state**. That is a core distinction
between a StateWork and a checklist.

## Relationship with the other systems

```text
CognitiveFrameWorks
    decides how work should be conducted

CognitiveStateWorks
    decides what domain state exists
    and which transitions are legal
```

For example, CFW/FUSE may require verification to exercise the changed
infrastructure boundary; Infrae declares the evidence required for
`CHANGING → VERIFIED`. CFW/WARD may require authority for a mutation; Infrae
declares that `PLANNED → CHANGING` is not legal until its transition requirements
are met.

DigitalPsychology observes agents traversing StateWorks and can ask whether they
skip `MODELED`, create unnecessary recovery loops, misuse specialists, declare
completion immediately after `VERIFIED`, or incur more correction cycles in one
flow than another.

DP may request a current-task activation or release from CSW's eligible,
composition-compatible choices. CSW validates and commits that request against the
selection revision. DP cannot create eligibility, rewrite StateWork invariants, or
declare `CHANGING → STABLE` legal because verification is inconvenient.

## The larger architecture

| System | Primary question |
| --- | --- |
| **CognitiveFrameWorks** | Which cognitive components and enforcement rules are available? |
| **CognitiveStateWorks** | Which workflow state and transitions are legal now? |
| **DigitalPsychology** | How should behavior adapt, and did the intervention improve progress? |

```text
       DigitalPsychology (optional external behavior controller)
                            │ private bounded decisions
                            ▼
                     Trusted execution host
                       /                 \
                      ▼                   ▼
             CFW components and      CSW workflow and
             action enforcement     durable state authority
                      \                   /
                       \                 /
                         Controlled agent
                                │
                    host actions and evidence
                                └──────────────► DP outcome evaluation
```

The diagram shows the full adaptive deployment. CSW remains usable alone, and
CFW+CSW can run together without DP. When DP is enabled, its outcome evaluator
uses host and CSW evidence to assess whether a targeted intervention improved
required-goal progress; the controlled agent's completion statement is not the
success signal.

## FreeInference Acknowledgment

This project was developed with the assistance of AI inference provided by [FreeInference.org](https://freeinference.org/).

This is an independent project. FreeInference did not review, sponsor, direct, supervise, approve, or endorse its development or contents. The project's design, implementation, claims, and maintenance are independent of FreeInference.

If you find this project useful, please consider supporting the infrastructure that helped make its development possible by donating to [FreeInference.org](https://freeinference.org/).
