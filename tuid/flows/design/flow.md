---
flow: design
required_specialists: ['../../aspects/feedback-states/aspect.md', '../../aspects/keyboard/aspect.md']
optional_specialists: []
---
# Flow: Design (MODELED → DESIGNED)

## Order

```text
USER TASK
   ↓
INFORMATION PRIORITY
   ↓
INTERACTION MODEL
   ↓
NAVIGATION MODEL
   ↓
REGIONS
   ↓
COMPONENTS
   ↓
RESPONSIVE BEHAVIOR
   ↓
VISUAL HIERARCHY
   ↓
TERMINAL CAPABILITY POLICY
   ↓
FAILURE / EMPTY / LOADING STATES
```

Do not begin by selecting border characters and colors.

## Design outputs

- **Regions** (`../../primitives/region/`) with purpose, priority, overflow behavior.
- **Interaction model** as intents (`MoveSelectionDown`, `OpenItem`, `CloseOverlay`) — not literal keys (see `../../aspects/keyboard/`).
- **Capability policy** per optional terminal feature: REQUIRED / PREFERRED / OPTIONAL / DISABLED (`../../aspects/terminal-capabilities/`).
- **Failure/empty/loading states** for every data-bearing component (`../../aspects/feedback-states/`).
- **Design system** for serious TUIs — tokens, component states, layout, interaction, capability policy — so no component independently chooses colors, borders, and key hints.

## Screen mode choice

Deliberately: **inline** (pickers, compact prompts, scrollback-persistent
results), **alternate screen** (dashboards, editors, browsers, monitoring),
or **overlay/summoned interaction** (temporary, underlying context stays
intact). Do not blindly make every TUI full-screen; do not blindly make every
utility inline.
