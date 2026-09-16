# Component: Status Bar

Persistent context strip.

```yaml
purpose: answer "where am I / what is happening / what can I do" persistently
state:      mode/location · async indicators · contextual hints
states:     (always present; content states per indicator)
concerns:
  - persistent status markers are clutter when static — clutter audit (../../aspects/layout/)
  - avoid permanent shortcut soup: contextual hints over exhaustive key map
  - async progress shows useful state, not just motion (../../aspects/feedback-states/)
  - status must be distinguishable from selection emphasis
overflow:   priority-ordered truncation — essential context survives narrowing
```
