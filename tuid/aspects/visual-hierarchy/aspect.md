# Aspect: Visual Hierarchy

A user should rapidly perceive:

```text
where am I?  what matters?  what is selected?
what is focused?  what changed?  what can I do?
```

## Emphasis signals, in preference order

position · whitespace · weight · brightness · foreground/background contrast ·
icon/symbol · border · label.

Do not make every element visually loud. Visual hierarchy should communicate
before decoration does. Clutter audit and the removal test live in
`../layout/`.

## Status and selection must differ

Status and selection using the same emphasis signal is a HIGH finding —
the user cannot tell what is selected from what is merely being displayed.
Similarly, loading and disconnected states must be visually distinguishable
(`../feedback-states/`).
