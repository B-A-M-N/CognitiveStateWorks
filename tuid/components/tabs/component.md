# Component: Tabs

Surface switcher.

```yaml
purpose: switch between major surfaces within a region
state:      tabs · active tab · per-tab view state
states:     empty (no tabs) · ready
concerns:
  - application navigation vs component navigation distinction (../../aspects/navigation/)
  - tab overflow: scroll vs condense — at narrow widths, deliberate
  - active tab indication without hue alone
  - per-tab state ownership: switching tabs preserves each tab's state
  - tab switch must not strand focus (hidden surface relinquishes focus)
overflow:   scroll/condense policy explicit
```
