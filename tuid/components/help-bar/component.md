# Component: Help Bar

Contextual key/affordance hints.

```yaml
purpose: discoverability without key-map memorization
state:      context (focused component / mode) · available actions
states:     per-context content · expanded (full help overlay handoff)
concerns:
  - contextual footer > permanent every-shortcut footer (../../aspects/keyboard/)
  - hints must match actual bindings — drift between hint and handler is a defect
  - hands off to full help overlay/palette for complete key map
overflow:   priority truncation; "?" style expansion for the rest
```
