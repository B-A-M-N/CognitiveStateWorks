---
flow: validate
operations: [validate, verify]
triggers: [validation_requested, behavior_claim]
states:
  from: [IMPLEMENTED, EXERCISABLE, VALIDATED]
  through: [VALIDATED]
completion:
  claim_classes:
    static_visual: {minimum_state: IMPLEMENTED, evidence_kinds: [rendered_observation]}
    responsive_layout: {minimum_state: EXERCISABLE, evidence_kinds: [rendered_viewport_matrix]}
    interaction: {minimum_state: VALIDATED, evidence_kinds: [interaction_validation]}
    terminal_lifecycle: {minimum_state: VALIDATED, evidence_kinds: [pty_validation]}
    legibility: {minimum_state: IMPLEMENTED, evidence_kinds: [rendered_observation]}
required_specialists: []
optional_specialists: []
---
# Flow: Validate (EXERCISABLE → VALIDATED)

## Questions

```text
Does the UI show the correct state?
Can the user identify where they are?
Can they identify what is selected? What is focused?
Can they identify what will happen next?
Can they recover from mistakes?
Does resizing preserve a coherent state?
Do overlays intercept input correctly?
Are asynchronous states visible?
Are failures actionable?
Does terminal restoration work?
Do unsupported terminal features degrade safely?
```

## Evidence, not assertion

Every answer requires evidence at the appropriate layer of the hierarchy
(`../SKILL.md`): "the panel is always visible" requires rendered/runtime
evidence; "resize works" requires multiple viewport states; "key handling
works in a terminal" may require PTY evidence. A compiled app is not a
validated interface; a passing snapshot does not prove interaction
semantics.

## Output

The Validation Packet (`../../primitives/evidence/`) — objective, invariant,
affected state/interaction/layout/render/terminal, evidence by layer,
regressions checked, known limitations, status.
