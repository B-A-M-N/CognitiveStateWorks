# Aspect: Terminal Lifecycle

Model:

```text
NORMAL TERMINAL → acquire terminal → enter application mode
→ configure required capabilities → run event/render loop
→ restore terminal → NORMAL TERMINAL
```

## Consider

raw mode · alternate screen · cursor · mouse reporting · focus reporting ·
bracketed paste · title · keyboard enhancement · teardown.

## Screen mode — choose deliberately

- **Inline** — pickers, compact prompts, bounded workflows, command results meant to remain in scrollback.
- **Alternate screen** — dashboards, editors, file browsers, monitoring, large persistent applications.
- **Overlay/summoned** — temporary interaction; underlying context stays conceptually intact.

Do not blindly make every TUI full-screen. Do not blindly make every utility inline.

## Terminal restoration is correctness, not polish

High-severity defects: shell remains in raw mode after exit; invisible cursor persists; mouse reporting persists; alternate screen remains active; input echo altered. Terminal lifecycle must be tested on **normal and abnormal exit paths** (`../../testing/pty-tests/`). Framework lifecycle facilities are generally preferred over hand-rolled cleanup — see `../../flows/recover/`.
