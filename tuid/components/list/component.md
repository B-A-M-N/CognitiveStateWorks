# Component: List

Collection navigation component.

```yaml
purpose: ordered selectable collection
state:      items · selection · scroll offset · filter (if any)
focusable:  yes
scrollable: yes
states:     empty (nothing exists) · no-match (filter) · loading · error · ready
concerns:
  - selection ≠ scroll position; moving selection may scroll into view; manual scroll need not move selection (../../aspects/scrolling/)
  - virtualization for large collections
  - selection visibly distinguishable from mere highlight
  - keyboard navigation via intents (MoveNext/MovePrev), mouse supplemental
overflow:   item truncation with ellipsis; horizontal policy explicit
```
