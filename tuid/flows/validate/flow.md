---
flow: validate
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
