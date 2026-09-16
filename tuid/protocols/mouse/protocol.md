# Protocol: Mouse Tracking

Mouse event encoding (SGR mouse mode and predecessors), wheel, drag, motion.

- Enable only when needed — tracking changes terminal behavior and must be restored on exit.
- Support varies by terminal and multiplexer; capability-gated (PREFERRED/OPTIONAL typically).
- Mouse supplements keyboard; the keyboard path must work with tracking disabled (test that rung).
