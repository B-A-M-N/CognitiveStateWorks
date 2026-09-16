# Aspect: Overlays

The overlay stack may include:

```text
base view → drawer → modal → command palette → confirmation
```

Define explicitly:

- render order
- input precedence
- focus ownership
- dismissal
- background behavior

Overlay behavior should not emerge accidentally from render order. The
routing contract puts the overlay stack above focused component and current
view in keybinding precedence (`../keyboard/`). Modal focus sequence (remember
→ capture → restore) is owned by `../focus/`. Overlays must remain within the
viewport at every supported size (responsive invariants).
