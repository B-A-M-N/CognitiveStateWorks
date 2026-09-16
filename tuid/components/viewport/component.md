# Component: Viewport

Generic scrollable content surface.

```yaml
purpose: window onto larger content
state:      content extent · offset · density policy
states:     fits (no scroll) · scrollable · at-top · at-bottom
concerns:
  - scroll indicators/position discoverable when content exceeds viewport
  - offsets clamped valid on resize and content change (responsive invariants)
  - content never renders outside allocated region (invariant)
  - scrollbar affordance when mouse supported
overflow:   this component's purpose; scroll vs crop explicit
```
