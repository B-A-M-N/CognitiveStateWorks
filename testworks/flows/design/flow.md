---
flow: design
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - design
---
# Design flow

**Purpose.** Choose independent behavioral oracles and a minimum useful fault-detection case set.

## Steps
1. Write a falsifiable protected behavior and failure hypothesis for each gap.
2. Choose oracle quality: deterministic expected output, state invariant, differential, metamorphic, property, contract or integration.
3. Prioritize negative, boundary, stateful, race, failure-recovery and security cases only where applicable.
4. Prove existing tests do not already supply equivalent detection; note fixture and environment cost.
5. Emit a test design with pass/fail observables and smallest scope consistent with the risk.

## Required outputs
- case specifications
- oracle evidence
- duplication assessment
- expected detection claims

## Stop / refuse
- No meaningful invariant or independent oracle
- Same defect is already credibly detected by an existing test

## Boundary
No source mutation; pass designed cases to generate when warranted.
