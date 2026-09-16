# Primitive: Interaction

A user intent derived from input.

```text
physical input → terminal event → key/mouse interpretation
→ interaction command → state transition
```

Reason in intents — `MoveSelectionDown`, `OpenItem`, `CloseOverlay`,
`SubmitForm`, `Cancel`, `FocusNext`, `ScrollPage` — rather than scattering
literal key handling throughout components. Physical keys stop at the
normalization boundary; protocol differences (`../../protocols/keyboard/`)
never leak below it. Interactions are the natural unit for state-transition
tests (`../../testing/state-tests/`).
