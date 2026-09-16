# Protocol: ANSI / VT Sequences

The base output protocol: styling (SGR), cursor addressing, screen modes,
clearing.

- The framework's renderer normally owns sequence generation — do not hand-roll output that competes with it (render ownership).
- Escape-sequence correctness across emulators is a terminal-profile-matrix concern, exercised via PTY tests when behavior matters.
- Alternate screen enter/exit, cursor show/hide, and mode-set sequences are lifecycle-critical: restoration on every exit path.
