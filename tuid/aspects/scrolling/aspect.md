# Aspect: Scrolling

A scrollable component owns:

```yaml
scroll:
  content_extent:
  viewport_extent:
  offset:
  selected_item:
  auto_scroll_policy:
```

Selection and scrolling are related but not identical:

- moving selection may scroll it into view
- manual scrolling need not always move selection

Scroll offsets must remain valid under resize and content changes (responsive
invariants). Follow mode, pause, and bounded memory for high-rate content are
Log Viewer pattern concerns (`../../patterns/log-viewer/`); unbounded log
rendering is an anti-pattern.
