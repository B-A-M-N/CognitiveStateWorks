# Component: Table

Tabular collection with columns.

```yaml
purpose: rows × columns with sorting/selection
state:      rows · columns · selection (cell or row — explicit) · sort · scroll (both axes)
states:     empty · no-match · loading · error · ready
concerns:
  - column width policy: fixed / weighted / content-derived; behavior when total > viewport
  - horizontal overflow: scroll vs truncate — deliberate per column
  - header visibility under vertical scroll
  - selection model explicit (row vs cell); sorting must not strand selection
overflow:   per-column policy; row truncation with ellipsis
```
