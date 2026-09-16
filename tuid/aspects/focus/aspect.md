# Aspect: Focus

One of the most frequently mishandled TUI concerns. Model it explicitly.

```text
focus owner → eligible input → component action
```

## FocusTarget (primitive: `../../primitives/focus-target/`)

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

## Required properties

- exactly defined owner
- visible indication — distinguishable without depending solely on hue
- predictable next/previous behavior
- no hidden focused control
- overlay focus capture
- restoration after overlay close

## Modal focus sequence

```text
modal opens → remember previous focus → focus modal
→ capture modal-relevant actions → modal closes → restore prior valid focus
```

Input must not leak through to the underlying surface. Modal input leaking is
HIGH severity (`../../flows/review/`).

Resize must not strand focus on an invisible component — hidden panes
relinquish focus (responsive invariants). Focus is application state, not
incidental rendering state (`../application-state/`).
