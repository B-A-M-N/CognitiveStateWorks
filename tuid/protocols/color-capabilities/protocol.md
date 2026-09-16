# Protocol: Color Capabilities

Color depth ladder: monochrome → 16 → 256 → truecolor.

- Detection via environment (COLORTERM, TERM) is heuristic — verify against what actually renders when fidelity matters.
- Design for graceful degradation down the ladder: semantic tokens (`../../aspects/color-theme/`) map to the best available depth.
- Contrast requirements survive every rung — readable contrast is an accessibility floor, not a truecolor feature.
