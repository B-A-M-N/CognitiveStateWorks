# Pattern: Command Center

Operational surface for invoking and monitoring actions (deploy/ops/control
workbench).

## Required aspects

action inventory (commands as data) · execution feedback (pending/success/
failure per action) · confirmation for destructive actions · output/log
surface per execution · history · concurrent operations.

## Notes

- Destructive actions trigger through unambiguous confirmation (BLOCKER
  severity if ambiguous — `../../flows/review/`).
- If this controls infrastructure, split concerns: tui'd owns interaction
  correctness; Infrae owns operation safety (`../../SKILL.md` relationships).
- Concurrent executions need per-operation status, not one global spinner.
- Execution output is a log viewport instance — bounded memory applies.
