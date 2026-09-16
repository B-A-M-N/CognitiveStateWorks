---
flow: interact
required_specialists: []
optional_specialists: []
---
# Flow: Interact (IMPLEMENTED → EXERCISABLE)

Exercise the interface. Interaction correctness requires more than individual
key handlers.

## Exercise

- keyboard
- focus movement and tab movement
- navigation (application, component, focus, viewport)
- selection
- text entry and paste
- scrolling
- command invocation and cancellation
- modal behavior (open, intercept, close, focus restore)
- mouse behavior where supported
- **resize during interaction**

## What counts

Each exercised path produces evidence about which layer owns correct
behavior: state, interaction interpretation, focus, layout, render,
terminal, async ordering, capability assumption. Defects found here route to
`../debug/` for layer attribution before any fix.
