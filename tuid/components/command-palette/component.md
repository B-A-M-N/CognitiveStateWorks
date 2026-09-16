# Component: Command Palette

Type-to-command invocation unifying discoverability.

```yaml
purpose: searchable command invocation
state:      commands (data) · query · matches · selection · context
states:     closed · open · no-matches · ready
concerns:
  - model commands as data: {id, label, shortcut, enabled, context, action}
  - context-aware enablement — commands invalid in current state are hidden or visibly disabled
  - do not build a palette for four obvious actions (pattern: ../../patterns/command-palette/)
  - overlay focus capture + restore on close (../../aspects/focus/)
  - shortcut display consistent with actual bindings — drift is a defect
overflow:   result list scrolls; query line fixed
```
