# Testing: Real PTY E2E

Layer 6. Real pseudo-terminal or equivalent emulator, where important.

Covers behaviors unit/render tests miss: raw mode, alternate screen, escape
sequences, resize, **terminal restoration** (normal and abnormal exit),
real input encoding, multiplexers, process exit, signals.

PTY tests are expensive — use strategically. Terminal restoration on
abnormal exit is the canonical PTY test: it cannot be faked at any lower
layer, and its failure is BLOCKER severity.
