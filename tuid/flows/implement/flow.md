---
flow: implement
states:
  through:
  - IMPLEMENTED
completion:
  claim_classes:
    static_visual:
      minimum_state: IMPLEMENTED
      evidence_kinds:
      - rendered_observation
    responsive_layout:
      minimum_state: EXERCISABLE
      evidence_kinds:
      - rendered_viewport_matrix
    interaction:
      minimum_state: VALIDATED
      evidence_kinds:
      - interaction_validation
    terminal_lifecycle:
      minimum_state: VALIDATED
      evidence_kinds:
      - pty_validation
    legibility:
      minimum_state: IMPLEMENTED
      evidence_kinds:
      - rendered_observation
framework_requirements:
- fuse
- ward
required_specialists: []
optional_specialists: []
when:
  all:
  - field: operation
    in:
    - implement
    - change
    - mutate
  - field: trigger
    in:
    - mutation
    - implementation
  - field: current_state
    in:
    - DESIGNED
---
# Flow: Implement (DESIGNED → IMPLEMENTED)

Implementation should preserve separation between:

```text
domain logic
state transitions
commands/effects
interaction mapping
layout
component rendering
terminal integration
```

Framework idioms may differ. The underlying boundaries should remain legible.

## Contracts to preserve during implementation

- **Input routing** — terminal input → normalize → global emergency → overlay stack → focused component → current view → application fallback. Every event has understandable ownership.
- **Rendering** — application state + terminal profile + viewport → layout → components → render frame → terminal backend. Rendering must not invent application semantics.
- **Async** — state requests effect → effect executes outside render → result becomes event → state decides whether the result remains relevant → render reflects state. Background workers must not arbitrarily paint the terminal.
- **Resize** — resize event → update viewport → recompute layout → reconcile visibility → reconcile focus → clamp selection/scroll → render.

## Framework selection

Choose by project requirements and ecosystem, never popularity alone:
implementation language, existing codebase, component model, styling, async,
performance, terminal control, testing, ecosystem, deployment — see
`../../frameworks/`. `tui'd` remains framework-neutral.
