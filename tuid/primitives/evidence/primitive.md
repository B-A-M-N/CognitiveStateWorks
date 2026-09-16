# Primitive: Evidence

Evidence hierarchy for TUI claims, weakest → strongest:

```text
source inspection
→ state/component tests
→ layout tests
→ render snapshot
→ interaction test
→ real PTY evidence
→ multi-size / terminal-profile evidence
→ actual user workflow evidence
```

Match evidence to claim:

| Claim | Requires |
|---|---|
| "The panel is always visible" | rendered/runtime evidence |
| "Resize works" | multiple viewport states |
| "Key handling works in a terminal" | PTY evidence |
| "Architecture separates state cleanly" | source/state-flow analysis |
| "Terminal restores on exit" | abnormal-exit PTY evidence |

The operator's description of the effective interface outranks source
inspection (User Observation Rule). Generated code and successful compilation
are never evidence that an observed defect disappeared.

## Validation Packet

A mature TUI change is emitted as the typed handoff packet in the common
envelope (`schemas/handoff-packet.schema.json`, composed by
`schemas/tui-validation-packet.schema.json`). Domain data lives in `payload`;
envelope fields are canonical and never re-declared:

```yaml
packet_id:
packet_type: tui_validation_packet
schema_version:
producer: "tui'd"
task_id:
subject_ref:
observed_at:
input_state:
output_state: validated
evidence_refs:
unknowns:
blockers:
authority:
invalidated_by:
recommended_next:

payload:
  objective:    { user_problem: }
  invariant:    { required_behavior: }
  state:        { affected_state: }
  interaction:  { affected_actions: }
  layout:       { affected_regions: tested_sizes: }
  render:       { expected_change: }
  terminal:     { affected_capabilities: }
  evidence:     { state_tests: layout_tests: snapshots: interaction_tests: pty_tests: }
  regressions:  { checked: }
  known_limitations:
  status:
```

This is the handoff contract to Getter (landing), review flows, and the
operator.
