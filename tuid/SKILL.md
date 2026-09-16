---
name: tuid
display_name: "tui'd"
description: >
  Terminal-user-interface domain system for designing, modeling, building,
  reviewing, testing, debugging, validating, and evolving interactive terminal
  applications. tui'd decomposes TUI work into explicit flows and specialist
  aspects covering terminal lifecycle, application state, rendering, layout,
  interaction, focus, components, navigation, visual language, responsive
  behavior, terminal capabilities, accessibility, asynchronous behavior,
  performance, robustness, testing, and framework-specific implementation.
  Use for new TUIs, existing-TUI audits, TUI redesigns, terminal interaction
  problems, component design, visual defects, input/focus defects, flicker,
  resize problems, testing, or architecture work. Not a Bubble Tea / Ratatui /
  Textual / Ink skill, styling guide, or component library — those are
  subordinate concerns under frameworks/. Framework-neutral by design.
---

# tui'd — Terminal User Interface Domain System

`tui'd` governs the TUI domain as a **CognitiveStateWork** — it implements the
protocol in `../PROTOCOL.md` for interactive terminal applications. This file
is the router and the state machine. Detailed knowledge lives in the files
that own it.

It reasons about the TUI as a complete interactive system:

```text
terminal (capabilities · lifecycle · input · output)
        │
        ▼
application state
        ▼
interaction model
        ▼
layout model
        ▼
component tree
        ▼
rendering
        ▼
visible terminal state
        ▼
human perception + action ──→ application state
```

The objective is not "render something attractive in a terminal." It is:

> Produce a terminal interface whose state, behavior, hierarchy, interaction,
> rendering, responsiveness, and failure behavior remain understandable and
> controllable under real terminal conditions.

---

## Core Doctrine

A TUI is an **interactive state machine rendered through a constrained,
capability-variable terminal surface**. Therefore:

```text
source code looks correct        ≠ rendered interface is correct
screenshot looks correct         ≠ interaction is correct
works at 160×50                  ≠ layout works at 80×24
keyboard works                   ≠ focus model is correct
widget exists                    ≠ widget state is legible
colors look attractive           ≠ hierarchy is understandable
snapshot matches                 ≠ real PTY behavior works
framework accepted the operation ≠ terminal state was restored correctly
```

`tui'd` evaluates the entire loop.

---

## StateWork protocol instantiation

**1. Domain.** Interactive terminal applications — their architecture,
interaction, rendering, and terminal integration. Not infrastructure (Infrae),
repository state (Gitter), or PR landing (Getter).

**2. State vocabulary.** `UNKNOWN, OBSERVED, MODELED, DESIGNED, IMPLEMENTED,
EXERCISABLE, VALIDATED, STABLE` plus failure states `DEFECTIVE,
DEGRADED, RECOVERY, FALLBACK`.

**3. State observations.** The rendered/runtime interface is the effective
state; source code is declared state. They disagree constantly. For an
existing TUI, run it whenever feasible — source-only inspection is
insufficient for rendering or interaction defects.

**4. Invariants.** See `primitives/invariant/`. Examples: exactly one text
field owns text input at a time; a modal intercepts commands that must not
reach the view beneath it; the focused control is visually distinguishable
without hue alone; the primary workflow remains usable without a mouse; no
viewport renders outside its allocated region; resize must not strand focus on
an invisible component; application exit restores terminal state; a background
operation may update application state but may not corrupt render ownership.

**5. Allowed transitions.** The state machine below. A TUI does not reach
`VALIDATED` merely by compiling or because one screenshot looks correct.

**6. Transition guards.** `IMPLEMENTED → EXERCISABLE` requires interaction
exercise (`flows/interact/`); `EXERCISABLE → VALIDATED` requires evidence at
the appropriate testing layer (`testing/`) per the evidence hierarchy.

**7. Evidence requirements.** Evidence hierarchy, weakest → strongest: source
inspection → state/component tests → layout tests → render snapshot →
interaction test → real PTY evidence → multi-size/profile evidence → actual
user workflow evidence. Match evidence to claim: "the panel is always visible"
requires rendered/runtime evidence; "resize works" requires multiple viewport
states; "key handling works in a terminal" may require PTY evidence.

**8. Mutation authority.** Render ownership: exactly one coherent layer owns
terminal drawing — never framework renderer + stray prints + background
writers competing. Input ownership: every event has understandable ownership
via the routing contract (`aspects/keyboard/`).

**9. Invalidation rules.** The User Observation Rule (`aspects/`): when the
operator says "the left panel only shows while typing," "focus is fucked,"
"that isn't the style I asked for" — that is **observed TUI evidence**. The
operator is describing the effective interface, not proposing a theory.
Reproduce and inspect rendered behavior; never answer "the component exists in
the code."

**10. Failure states.** `DEFECTIVE` (broken invariant, rendering
instability), `DEGRADED` (unusable viewport), `RECOVERY` (terminal
corruption), `FALLBACK` (unsupported capability).

**11. Recovery transitions.** See `flows/recover/`: application exits →
terminal modes restored → cursor restored → input usable → shell remains
sane. Terminal restoration is correctness, not polish.

**12. Completion states.** `VALIDATED`/`STABLE` require the completion
standard: architecture understandable, state ownership explicit, interaction
routing understandable, focus deterministic, layout handles supported
viewports, components expose complete meaningful states, visual hierarchy
legible, color not the sole semantic signal, capability policies deliberate,
async work does not corrupt interaction/rendering, render ownership coherent,
terminal restoration on normal and important abnormal exits, evidence at the
appropriate layer, known limitations explicit. Perfect aesthetics and
universal compatibility are not required — the interface must behave
deliberately within its declared operating envelope.

**13. Handoff contracts.** The Validation Packet (`primitives/evidence/`) and
the TUI Audit Matrix (`flows/review/`). To Getter: TUI-specific validation
evidence for PR landing. To Infrae: if a TUI controls infrastructure, tui'd
answers "is the interaction understandable and correct?" and Infrae answers
"is the requested infrastructure operation safe and correct?" — neither
absorbs the other.

---

## State machine

```text
UNKNOWN ──discover──→ OBSERVED ──model──→ MODELED ──design──→ DESIGNED
      ──implement──→ IMPLEMENTED ──render+interact──→ EXERCISABLE
      ──validate──→ VALIDATED ──operational use──→ STABLE

Exceptional transitions (from ANY state):
  observed contradiction   → OBSERVED
  broken invariant         → DEFECTIVE
  unusable viewport        → DEGRADED
  terminal corruption      → RECOVERY
  input ambiguity          → OBSERVED
  rendering instability    → DEFECTIVE
  unsupported capability   → FALLBACK
```

## Router

Match the task to the file that owns it. Load only what is relevant.

| Task shape | Go to |
|---|---|
| Existing TUI, unknown behavior | `flows/discover/` |
| Architecture / state ownership / component tree | `flows/model/`, `aspects/application-state/`, `aspects/architecture/` |
| New interface or redesign | `flows/design/` or `flows/redesign/`, then `patterns/` |
| Building it | `flows/implement/`, `components/`, `frameworks/` |
| Input, keys, focus, mouse, paste | `aspects/keyboard/`, `aspects/focus/`, `aspects/mouse/`, `aspects/text-input/` |
| Layout, resize, overflow, clutter | `aspects/layout/`, `aspects/responsive/` |
| Visual defects, hierarchy, color, text | `aspects/visual-hierarchy/`, `aspects/color-theme/`, `aspects/text-unicode/` |
| Blank/stuck/error surfaces | `aspects/feedback-states/`, `aspects/async-behavior/` |
| Flicker, slowness, redraw | `aspects/rendering/`, `aspects/performance/` |
| Terminal corruption, raw-mode leak, exit behavior | `flows/recover/`, `aspects/terminal-lifecycle/` |
| Capability questions (color, mouse, enhanced keyboard, graphics) | `aspects/terminal-capabilities/`, `protocols/` |
| Testing strategy or gaps | `flows/test/`, `testing/` |
| Debugging by symptom | `flows/debug/` |
| Audit or review | `flows/review/` |
| Framework-specific mechanics | `frameworks/` |

## Relationship to CognitiveFrameWorks

FrameWorks supplies the reasoning disciplines — evidence over assumption,
observation handling, decomposition, verification, God Object resistance.
`tui'd` applies them to the terminal-interface domain.

## Relationship to CognitiveStateWorks

The StateWork protocol (`../PROTOCOL.md`) supplies states, transitions,
guards, evidence, invalidation, recovery, completion. `tui'd` defines the
TUI-domain state machine and domain-specific transition requirements — e.g.,
`IMPLEMENTED` may transition to `VALIDATED` only when the relevant render,
interaction, viewport, and terminal invariants have been demonstrated.

## Final Principles

> A TUI is a stateful application, not decorated stdout.
> Focus is state. Layout is behavior. Resize is normal operation.
> The terminal is a variable-capability client.
> Rendering is not correctness. A screenshot is not interaction evidence.
> Input ownership must be explicit.
> Async work must return through controlled state transitions.
> Every important component needs meaningful non-happy states.
> Terminal restoration is correctness.
> Compatibility should be progressive rather than imaginary.
> Visual hierarchy should communicate before decoration does.
> The interface observed by the user is more authoritative than what the code
> says should have rendered.
> If the operator says the panel disappears, inspect why the panel disappears.
> Do not use implementation as evidence that implementation worked.
