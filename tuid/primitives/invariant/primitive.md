# Primitive: Invariant

What must remain true across any legal transition.

## Examples

```text
Exactly one text field owns text input at a time.
A modal intercepts commands that must not reach the view beneath it.
The focused control is visually distinguishable without depending solely on hue.
The primary workflow remains usable without a mouse.
No viewport may render content outside its allocated region.
Resize must not strand focus on an invisible component.
Application exit restores terminal state.
A background operation may update application state but may not corrupt render ownership.
```

These are stronger than arbitrary aesthetic rules. Invariants gate
transitions: `IMPLEMENTED → VALIDATED` requires the relevant render,
interaction, viewport, and terminal invariants demonstrated. Broken invariant
→ `DEFECTIVE` from any state.
