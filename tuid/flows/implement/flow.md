---
flow: implement
operations: [implement, change, mutate]
triggers: [mutation, implementation]
states:
  from: [DESIGNED]
  through: [IMPLEMENTED]
framework_requirements: [fuse, ward]
required_specialists: []
optional_specialists: []
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
