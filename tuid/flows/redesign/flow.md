---
flow: redesign
required_specialists: []
optional_specialists: []
---
# Flow: Redesign (any state → DESIGNED)

A redesign starts from workflow and information architecture — not from the
existing component tree:

```text
current user task
       ↓
current friction
       ↓
information hierarchy
       ↓
interaction hierarchy
       ↓
region hierarchy
       ↓
new component model
       ↓
visual treatment
```

Do not retain a bad information architecture merely because its ASCII drawing
looks familiar. Do not redesign visual treatment before the region and
interaction hierarchies are settled — that produces a reskinned defect.

## Method

1. Run `../discover/` and `../model/` on the current interface first — a redesign of an unmodeled TUI is guesswork.
2. Identify friction from the **user's** task flow, not from code organization.
3. Rebuild information → interaction → region hierarchies; carry forward what the workflow actually needs.
4. Map the new component model, preserving component contracts (`../../components/`).
5. Visual treatment last. Validate through `../validate/` — redesigns get no exemption from evidence.
