# Component: Drawer

Slide-in panel over/beside content.

```yaml
purpose: secondary surface without full-screen navigation
state:      open/closed · content · width/position
states:     closed · open · (content states)
concerns:
  - narrow-viewport role: drawer is the standard degradation for hidden navigation (../../aspects/responsive/)
  - focus moves into drawer on open, returns on close
  - input interception boundary explicit (modal-like capture or passthrough — chosen)
  - animation without blocking input; resize while open re-fits
overflow:   content scrolls; drawer bounds within viewport
```
