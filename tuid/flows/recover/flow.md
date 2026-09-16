---
flow: recover
required_specialists: []
optional_specialists: []
---
# Flow: Recover (RECOVERY / DEFECTIVE → STABLE)

TUI recovery covers abnormal terminal/application exit and terminal
corruption.

## Triggers

- panic
- SIGTERM / signals
- cancelled async operation mid-render
- broken render
- raw-mode leak
- alternate-screen leak
- cursor left hidden
- mouse tracking left enabled

## Desired outcome

```text
application exits
      ↓
terminal modes restored
      ↓
cursor restored
      ↓
input usable
      ↓
shell remains sane
```

## Rules

- Framework lifecycle facilities should generally be preferred over
  hand-rolled terminal cleanup.
- Terminal restoration is **correctness, not polish** — a shell left in raw
  mode or with mouse reporting enabled is a BLOCKER-severity defect.
- Test terminal lifecycle on **normal and abnormal exit paths** (`../../testing/pty-tests/`).
- After recovery, validate through `../validate/` — restoration succeeded
  only if the terminal is actually restored, not merely if the exit handler
  was reached.
