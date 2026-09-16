# Pattern: Terminal Workspace

Complex TUI environments: workspace manager, window/pane tree, focus manager,
input router, overlay manager, terminal emulator surface, session state.

## Notes

**Keep those responsibilities separate.** A window manager must not quietly
become application state + terminal emulation + process management + styling
in one object — that is the TUI God Object at pattern scale
(`../../aspects/architecture/` God Object detection).

- Each responsibility is its own boundary with its own state ownership.
- Session persistence (layout, panes, focus) is explicit session state with a
  schema — not ad-hoc globals.
- If embedded terminals exist, the embedded emulator surface is a component
  with its own input ownership contract; input routing between host
  application and embedded terminal must be explicit (focus capture policy).
- This pattern composes other patterns (dashboard regions, log viewports,
  pickers) — it does not replace their contracts.
