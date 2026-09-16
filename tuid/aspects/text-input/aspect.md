# Aspect: Text Input

Handle separately:

```text
typing · paste · selection · cursor · deletion · word movement · history
completion · validation · submission · cancellation
```

## Paste is not typing

Pasted text is not equivalent to a series of human key presses. Where
supported, bracketed paste permits distinguishing the two (protocol mechanics
in `../../protocols/bracketed-paste/`). A paste handler that replays paste as
keystrokes can trigger shortcut actions, corrupt forms, or overflow single-key
inputs.

Exactly one text field owns text input at a time (invariant) — focus
ownership (`../focus/`) determines which.
