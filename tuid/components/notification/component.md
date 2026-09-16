# Component: Notification

Transient message surface.

```yaml
purpose: surface outcomes/events without navigating
state:      queue · severity · timing · dismissal
states:     visible · expiring · dismissed · (severity: info/success/warning/error)
concerns:
  - severity via symbol + text + color (never color alone)
  - error notifications actionable or link to details — no dead-ends
  - timing: errors persist until dismissed; transient info may auto-expire
  - must not steal focus from the user's current work (unless action required)
  - queue policy: rapid events coalesce, don't stack-flicker
overflow:   bounded visible queue; stacking order explicit
```
