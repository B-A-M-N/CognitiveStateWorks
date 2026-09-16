# Aspect: Responsive

Terminal resize is **normal behavior**, not an exceptional event.

## Degradation priorities — define them explicitly

Example ladder:

```text
WIDE        Nav | Content | Detail
STANDARD    Nav | Content        — detail becomes overlay
NARROW      Content              — navigation becomes drawer
CONSTRAINED essential workflow only
TOO SMALL   clear minimum-size message
```

Do not simply crop the wide layout. Do not hard-code density classes to
arbitrary universal dimensions — the application determines its truthful
minimum (see `../../primitives/viewport/`).

## Responsive invariants on resize

- focused item remains discoverable
- selected item remains valid
- essential actions remain available
- hidden panes relinquish focus
- overlays remain within viewport
- content does not render beyond boundaries
- scroll offsets remain valid

Resize is exercised during interaction (`../../flows/interact/`), tested at
multiple fixed dimensions (`../../testing/layout-tests/`), and debugged as a
potential cross-layer defect — a focus defect after resize is a focus-ownership
defect, not a layout one.
