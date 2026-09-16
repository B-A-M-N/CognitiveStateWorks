---
flow: test
required_specialists: []
optional_specialists: []
---
# Flow: Test (building the evidence base)

Use the layered test model (`../../testing/`). The base should contain many
deterministic tests; real-terminal tests should be fewer but strategically
important.

## Layer order

```text
state/update tests (many, deterministic)
  → component tests
  → layout tests (fixed dimensions, invariant assertions)
  → snapshot/golden tests (regression evidence, not interaction proof)
  → interaction tests (state + visible result)
  → real PTY E2E (few, strategic)
  → terminal profile matrix (only where portability matters)
```

## Rules

- Layout tests assert **region invariants**, not merely pretty snapshots: regions don't overlap unexpectedly, modal fits viewport, primary content remains nonzero, hidden pane cannot own focus.
- Snapshots require deterministic dimensions, color profile, data, timestamps, animation state.
- Interaction tests assert both state **and** visible result.
- PTY tests are expensive — use them for behaviors unit/render tests miss: raw mode, alternate screen, escape sequences, resize, terminal restoration, real input encoding, multiplexers, signals.
- Do not pretend exhaustive terminal compatibility is practical if the project does not require it. Test representative profiles only.
- Visual review inspects hierarchy, density, alignment, spacing, clipping, overflow, focus, selection, error/loading/empty states, narrow and wide states — a screenshot of the default happy state is weak evidence.
