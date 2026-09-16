# Aspect: Application State

## The four state classes — do not mix them indiscriminately

```text
DOMAIN STATE      what the application knows
INTERACTION STATE what the user is currently doing
VIEW STATE        what portion of state is currently shown
EPHEMERAL STATE   hover, transient messages, animation, pending key sequences
```

## State ownership

A common TUI failure is one giant model containing application data,
navigation, dimensions, modal state, input, async operations, rendering
flags, and every widget's local state. Prefer explicit ownership:

```text
AppState
├── DomainState
├── NavigationState
├── WorkspaceState
├── OverlayState
└── SessionState

Components
├── ListState
├── TableState
├── InputState
└── ViewportState
```

Central coordination does not require centralized ownership of every detail.

Focus is application state — it must not exist only as incidental rendering
state (see `../focus/`). Selection and scroll offsets are state with validity
invariants under resize.
