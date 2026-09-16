# Primitive: FocusTarget

Anything eligible to receive contextual input.

```yaml
focus_target:
  id:
  component:
  order:
  visible:
  enabled:
  focused:
  accepts_text:
  available_actions:
```

Focus is application state — it must not exist only as incidental rendering
state. The `visible` field is load-bearing: a target that becomes invisible
on resize without relinquishing focus violates the resize invariant. Focus
properties and modal sequence in `../../aspects/focus/`.
