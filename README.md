# CognitiveStateWork

Operational skills for understanding, transitioning, validating, and
recovering **domain state**. Sibling to CognitiveFrameWorks (`~/CognitiveFrameWorks`),
which governs how an agent reasons; this tree governs what an agent knows
about state and which transitions are legal.

```text
CognitiveFrameWorks            CognitiveStateWork
how should I think?            what state am I in?
  evidence discipline            states & vocabulary
  assumption control             legal transitions & guards
  observation handling           evidence requirements
  decomposition                  invalidation & recovery
         │                              │
         └──────── reasoning policy ────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
     Infrae          Gitter          Getter
 infrastructure    repository      repository
    states         observation       mutation
        ▲
        │
      tui'd (terminal-interface states)
```

## Contents

- [`PROTOCOL.md`](PROTOCOL.md) — the 13-element protocol every StateWork implements
- [`registry.yaml`](registry.yaml) — the registry: every StateWork's manifest id
- [`RUNTIME.md`](RUNTIME.md) — the tiny kernel an active model carries
- [`schemas/`](schemas/) — manifest schema, common handoff envelope, per-packet
  composed schemas, and the packet registry
- [`infrae/`](infrae/) — **Infrae**: infrastructure StateWork (STATEWORK.md + 11 flows + 9 domains + primitives + policies)
- [`tuid/`](tuid/) — **tui'd**: terminal user interface StateWork (SKILL.md router + 11 flows + 24 aspects + 19 components + 11 patterns + 8 testing layers + 5 framework adapters + 9 protocols + 11 primitives)
- [`gitter/`](gitter/) — **Gitter**: repository truth & isolation (observation phase)
- [`getter/`](getter/) — **Getter**: repository mutation & recovery (mutation phase)

## Discovery and routing vs runtime activation

The model changed from "skills activate contextually by header language"
to **explicit registration**:

- **Discovery and routing** = `registry.yaml` + each StateWork's
  `manifest.yaml` (id, triggers, phase, inputs.required/optional (typed handoff
  packets), emits, core requirements, runtime.specialists, version, handoff
  packet type). `resolve-runtime.py` reads these; cogframe
  does not hard-code StateWork vocabulary.
- **Runtime activation** = conditional, decided by the resolver against the
  actual task: the profile kernel, the best-matching StateWork, its required
  handoff-packet producers, and its `core_requirements` merged into the
  active kernel.
- **Registration ≠ loading.** A registered StateWork costs no active context
  until the resolver selects it. Loading happens only for the selected chain.

## Handoffs

StateWorks never call each other directly. Domain changes are transmitted as
typed handoff packets in the common envelope
(`schemas/handoff-packet.schema.json`); per-packet schemas compose that
envelope (`allOf`) and carry domain data in `payload`. Registered packet
types with producers/consumers live in `schemas/packet-registry.yaml`.

## Validation

```bash
python3 scripts/validate-stateworks.py
```

Checks registry validity, manifest schema conformance, unique ids, entrypoint
existence, packet registration, producer/consumer consistency, recognized
FrameWorks `core_requirements`, and handoff fixtures against composed schema.

## Two framework-level principles

Imported into CognitiveFrameWorks' core doctrine because they apply beyond any
one domain:

1. **Agent action is not evidence of correctness.** "Implemented," "fixed,"
   and "done" close nothing by themselves; results must be re-observed.
2. **Operator observations invalidate stale assumptions.** "That's still
   broken" reopens the state; it is never a casual remark.

## Future StateWorks

The protocol is designed for reuse: deployment state, security incident state,
data migration state, release state, and PR lifecycle state can each become a
StateWork without changing this tree's shape — add a directory, a manifest,
and a registry entry.
