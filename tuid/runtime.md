# tuid — Runtime Capsule

Terminal UI engineering discipline. Owns rendering, layout, focus, input,
flicker, resize, terminal capabilities, corruption handling.

## State vocabulary
Use only states and transitions declared in transitions.yaml. The runtime
resolver pins that contract; this capsule does not define a second state
machine. Normal path: UNKNOWN → OBSERVED → MODELED → DESIGNED → IMPLEMENTED
→ EXERCISABLE → VALIDATED → STABLE.

## Flow router
Pick one active flow from flows/ (debug, design, discover, implement,
interact, model, recover, redesign, review, test) and load at most two
relevant specialists from aspects/ — never the whole tree.

## Invariants
- Rendering must be deterministic for a given terminal state; layout must
  degrade under resize and capability loss.
- Validate with a real PTY when behavior claims are made (testing/pty-tests),
  not by visual inspection alone.
- Invalid input, focus loss, and corruption states must be explicitly
  handled, never silently ignored.

## Exit produced
Emit `tui_validation_packet` with component, checks, result.

## Completion
Done when the component renders, interacts, and validates under the claimed
terminal capabilities, and a validation packet is emitted.
