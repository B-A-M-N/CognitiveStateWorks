# Component: Inspector

Detail pane bound to selection.

```yaml
purpose: show detail for the current selection
state:      bound selection · content · loading (per selection)
states:     no-selection · loading · ready · error · stale-selection
concerns:
  - no-selection state is a first-class state, not blank
  - binding must track selection identity — async detail for selection A must not render for selection B (stale-result rule, ../../aspects/async-behavior/)
  - responsive role: first thing degraded to overlay at narrow widths
  - selection change during load: latest selection wins
overflow:   internal scroll; key-value truncation policy
```
