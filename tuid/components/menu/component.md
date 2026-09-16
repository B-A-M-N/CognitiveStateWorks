# Component: Menu

Action list (contextual or primary).

```yaml
purpose: present and invoke actions
state:      items · enabled/disabled · selection · open/closed
states:     closed · open · empty (no actions apply) · filtered (if search)
concerns:
  - dismissal policy: explicit key, click-away where mouse, cancellation intent
  - disabled items visible but non-selectable; reason discoverable (help)
  - shortcuts shown but not duplicated soup (../../aspects/keyboard/ discoverability)
  - overlay precedence when invoked over content (../../aspects/overlays/)
overflow:   scroll with selection kept visible
```
