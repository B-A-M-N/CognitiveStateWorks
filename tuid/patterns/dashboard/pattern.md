# Pattern: Dashboard

Typical regions:

```text
┌──────────────────────────────────────────────────┐
│ Header / Context                                 │
├────────────┬──────────────────────┬───────────────┤
│ Navigation │ Primary Information  │ Detail        │
├────────────┴──────────────────────┴───────────────┤
│ Status / contextual actions                      │
└──────────────────────────────────────────────────┘
```

On narrow terminals, detail becomes conditional or overlayed rather than
crushing primary content (responsive ladder, `../../aspects/responsive/`).
Alternate screen is the natural mode. Detail pane = Inspector component
(component contract governs stale-selection binding). Avoid border soup in
the region split — spacing and placement before borders.
