# Protocol: Bracketed Paste

Delimits pasted content so the application can distinguish paste from typing.

- Without it, paste is indistinguishable from rapid keystrokes — shortcuts can fire, forms can corrupt (`../../aspects/text-input/`).
- Capability-gated: when unavailable, treat paste conservatively (e.g., disable single-key actions during high-rate input is NOT generally detectable — document the fallback honestly).
- Mode must be disabled on exit (lifecycle restoration).
