# Aspect: Architecture

## Recognized patterns

**Model–Update–View** — Event → Update → Model → View. Natural for
event-driven TUIs (Bubble Tea).

**Component/Reactive** — State → component tree → reconciliation → terminal
output (Ink, Textual).

**Retained Widget Tree** — widgets → message/event routing → reactive state →
layout/render.

`tui'd` adapts to the chosen framework without forcing another framework's
architecture onto it. See `../../frameworks/`.

## Architecture boundaries to preserve

Whatever the pattern, keep separable:

```text
domain logic / state transitions / commands-effects / interaction mapping /
layout / component rendering / terminal integration
```

## TUI God Object detection

Warning signs: one `App` handles every key; one `Update` contains every
interaction; one render method builds the entire application; every screen
reads every state field; modal behavior scattered everywhere; layout math
throughout rendering; input routing and business logic inseparable; every
feature edits the same file; async operations mutate UI state from arbitrary
locations; component boundaries exist visually but not architecturally.

Response: identify state / interaction / render / layout / effect ownership
first, then separate along actual responsibility boundaries — not into dozens
of reflexive micro-components.
