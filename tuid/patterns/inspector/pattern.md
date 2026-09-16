# Pattern: Inspector

Selection-driven detail surface.

```text
selection → detail binding → rendering
```

## Required aspects

selection identity tracking · async detail loading per selection ·
no-selection state · stale-selection guard · refresh · internal navigation
(nested detail).

## Notes

- The stale-result rule is the core contract: detail for selection A must
  never render while selection B is current.
- No-selection is a first-class state.
- As a region, the inspector is typically the first thing degraded to overlay
  at narrow widths (`../../aspects/responsive/`).
- Works as the Detail pane of the dashboard pattern or the right pane of
  split-pane.
