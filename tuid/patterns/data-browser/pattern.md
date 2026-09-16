# Pattern: Data Browser

```text
query / filter → collection → selection → detail / inspector
```

## Required aspects

filtering · sorting · pagination/virtualization · selection · detail · empty
result · loading · data refresh.

## Notes

- Virtualization for large collections (10,000 rows is a robustness test case).
- Empty result must differentiate filter-no-match from data-failed-to-load.
- Detail binding tracks selection identity — stale-result rule applies
  (`../../aspects/async-behavior/`).
- Refresh must not strand selection or lose scroll position deliberately kept.
- Works in both inline (picker-like browsers) and alternate screen; size drives
  screen-mode choice.
