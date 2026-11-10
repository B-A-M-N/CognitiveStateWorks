---
flow: generate
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - generate
---
# Generate flow

**Purpose.** Construct or propose executable tests with trustworthy oracles and reproducible fixtures.

## Steps
1. Match repository language, test structure, fixture lifetime and isolation boundaries; remain stack agnostic.
2. Create deterministic fixtures; control time, randomness, external services and concurrency where possible.
3. Assert externally meaningful behavior and explicit negative paths, not incidental implementation details.
4. Demonstrate that the test fails for the intended regression when practical (mutation, pre-fix reproduction, or controlled negative).
5. Check test code itself, isolate additions, and issue a bounded mutation handoff to Getter.

## Required outputs
- test change proposal
- proof of oracle sensitivity
- test fixture specification
- expected run command

## Stop / refuse
- Repository ownership or mutation authority is unknown
- Only tautological tests are possible
- Generated tests duplicate coverage with no additional detection

## Boundary
TestWorks may author proposed diffs in isolated artifacts; Getter owns integration into repository state.
