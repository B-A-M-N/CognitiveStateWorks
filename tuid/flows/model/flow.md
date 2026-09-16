---
flow: model
required_specialists: ['../../aspects/application-state/aspect.md']
optional_specialists: []
---
# Flow: Model (OBSERVED → MODELED)

Construct explicit models for:

```text
component hierarchy
state ownership
interaction routing
focus graph
navigation graph
layout tree
overlay stack
render pipeline
async event flow
terminal lifecycle
```

## Component hierarchy example

```text
App
├── Header
├── Workspace
│   ├── NavigationPane
│   │   └── List
│   ├── MainPane
│   │   ├── Tabs
│   │   └── Content
│   └── DetailPane
├── StatusBar
├── CommandBar
└── OverlayStack
    ├── CommandPalette
    └── HelpModal
```

## State ownership model

Separate (see `../../aspects/application-state/`):

```text
AppState
├── DomainState       what the application knows
├── NavigationState   where the user is
├── WorkspaceState    layout/regions
├── OverlayState      modal stack
└── SessionState      session-persistent choices
```

Central coordination does not require centralized ownership of every detail.

## God Object detection

Warning signs: one `App` handles every key; one `Update` contains every
interaction; one render method builds the entire application; every screen
reads every state field; modal behavior is scattered everywhere; layout math
appears throughout rendering; input routing and business logic are
inseparable; every feature edits the same file; async operations mutate UI
state from arbitrary locations; component boundaries exist visually but not
architecturally.

Do not respond by blindly making dozens of tiny components. First identify
state / interaction / render / layout / effect ownership, then separate along
actual responsibility boundaries.
