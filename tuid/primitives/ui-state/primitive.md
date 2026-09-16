# Primitive: UIState

Meaningful application state, classed:

```text
DOMAIN STATE      what the application knows
INTERACTION STATE what the user is currently doing
VIEW STATE        what portion of state is currently shown
EPHEMERAL STATE   hover, transient messages, animation, pending key sequences
```

Do not mix these indiscriminately. Class determines lifetime, persistence,
and testability: domain state survives sessions (sometimes), interaction
state survives renders, ephemeral state may not even survive a frame. State
ownership structures in `../../aspects/application-state/`.
