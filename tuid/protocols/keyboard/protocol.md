# Protocol: Keyboard Input

Physical encoding of key events, legacy vs enhanced.

- Legacy encoding cannot reliably represent all key combinations (ambiguous modifiers, missing release events).
- Enhanced protocols (e.g., kitty keyboard protocol) add disambiguation, release events, modifier fidelity, key encodings — capability-gated, progressively enabled.
- The application maps normalized events to intents; protocol differences stop at the normalization boundary (`../../aspects/keyboard/`).
- Test at both encoding rungs when the capability policy claims legacy fallback.
