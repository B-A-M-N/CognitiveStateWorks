---
flow: discover
states:
  through:
  - OBSERVED
fallback: true
required_specialists:
- ../../aspects/terminal-capabilities/aspect.md
optional_specialists: []
when:
  all:
  - field: operation
    in:
    - discover
    - inspect
  - field: trigger
    in:
    - discovery_requested
    - unknown_state
  - field: current_state
    in:
    - UNKNOWN
---
# Flow: Discover (UNKNOWN → OBSERVED)

Purpose:

> Establish actual TUI behavior before changing it.

## Inspect

```text
application architecture
component tree
state ownership
input routing
focus ownership
layout computation
screen mode
render lifecycle
terminal capabilities
theme system
async work
test coverage
known defects
```

For an existing TUI, **run it whenever feasible**. Source-only inspection is
insufficient for rendering or interaction defects — the code is declared
state; the rendered interface is effective state, and they disagree.

## Output

```yaml
state: OBSERVED
architecture:
components:
interaction:
layout:
terminal_behavior:
visual_language:
tests:
known_defects:
unknowns:
```

Capability detection is part of discovery — see
`../../aspects/terminal-capabilities/` for progressive detection rather than
assumption.
