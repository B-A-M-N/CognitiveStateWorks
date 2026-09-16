# Component: Tree

Hierarchical collection.

```yaml
purpose: expandable hierarchy navigation
state:      nodes · expansion · selection · scroll
states:     empty · loading · error · ready
concerns:
  - expansion state survives navigation/refresh deliberately (session state vs ephemeral — explicit)
  - depth indentation at narrow widths; deep nesting policy
  - selection vs focus within tree; keyboard collapse/expand via intents
overflow:   line truncation; indentation budget under narrow viewports
```
