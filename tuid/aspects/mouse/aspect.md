# Aspect: Mouse

Mouse support should generally **supplement, not destroy, keyboard usability**.
The primary workflow remains usable without a mouse (invariant).

## Consider

click · double click · wheel · drag · hover · selection · scrollbar · resize
affordance.

Mouse tracking changes terminal behavior and should be enabled only when
needed — and restored on exit (`../terminal-lifecycle/`). Protocol mechanics
in `../../protocols/mouse/`; capability policy in
`../../aspects/terminal-capabilities/`.
