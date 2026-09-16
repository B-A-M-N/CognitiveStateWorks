# Component: Log Viewport

High-rate streaming text surface.

```yaml
purpose: display streaming/appended log content
state:      buffer (bounded) · follow mode · paused · scroll offset · filters · search
states:     empty · streaming · paused · filtered · backtracked
concerns:
  - bounded memory — unbounded log rendering is an anti-pattern (pattern: ../../patterns/log-viewer/)
  - follow vs pause: user scroll pauses follow (or explicit pause); resume must be explicit or obvious
  - severity styling without color-only semantics; horizontal overflow policy (wrap vs scroll)
  - timestamps, filtering, search per pattern contract
  - high event rate: coalesce renders (rendering budget, ../../aspects/performance/)
overflow:   horizontal policy explicit; buffer eviction policy explicit
```
