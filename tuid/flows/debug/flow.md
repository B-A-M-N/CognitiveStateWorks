---
flow: debug
operations: [debug, diagnose, inspect]
triggers: [observation, contradiction]
states:
  from: [IMPLEMENTED, DEFECTIVE]
  through: [DEBUGGED]
framework_requirements: [owl, anchor]
required_specialists: []
optional_specialists: []
---
# Flow: Debug (any state, by layer attribution)

Debug by layer — **do not patch rendering until determining which layer
actually owns the defect**:

```text
STATE       Is application state wrong?
INTERACTION Was the input interpreted incorrectly?
FOCUS       Did the wrong component receive input?
LAYOUT      Was the region computed incorrectly?
RENDER      Was correct state rendered incorrectly?
TERMINAL    Did the emulator interpret output differently?
ASYNC       Did event ordering produce stale state?
CAPABILITY  Was unsupported behavior assumed?
```

## Method

1. Reproduce the defect (rendered/runtime — source inspection alone cannot attribute a rendering or interaction defect).
2. Attribute the layer by tracing the pipeline: input → interpretation → interaction command → state transition → layout → render frame → terminal output.
3. Fix in the owning layer. A focus defect patched in render code will recur.
4. Add regression evidence at the testing layer appropriate to the defect (`../test/`).

## Symptom hints

- **Flicker** — investigate unnecessary full redraw, layout instability, frame clearing, concurrent output, rapid state toggling, size oscillation, animation frequency, protocol behavior. Do not "fix" flicker by reducing update rate before identifying its source.
- **Wrong data shown** — check the async/stale-result path first: associate async results with the state/request that produced them.
- **Input does nothing / does the wrong thing** — trace the input routing contract; check overlay precedence and focus ownership before suspecting the key handler.
- **Corruption after exit** — terminal lifecycle; see `../recover/`.
