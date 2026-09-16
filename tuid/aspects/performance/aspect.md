# Aspect: Performance

Measure:

```text
event processing latency · state-update cost · layout cost · render cost
output volume · frame frequency · async backlog · memory growth
```

A TUI often feels slow because of: excessive rendering, expensive layout,
blocking I/O in the update path, unbounded logs, unnecessary animations,
enormous component state.

## Rendering budget

Do not redraw constantly merely because a timer can fire constantly. Prefer
event-driven rendering unless continuous animation or time-sensitive display
actually requires periodic updates. Unbounded log rendering is an anti-pattern
— log viewport components need bounded memory (`../../components/logs/`).

Performance findings attribute by layer via `../../flows/debug/` — slowness
from blocking I/O in the update path is an async defect, not a render defect.
