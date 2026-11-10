---
flow: select
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - select
---
# Select flow

**Purpose.** Select the smallest defensible execution plan based on risk and current receipts.

## Steps
1. Start with mandatory critical invariants and changed behavior; model fault boundaries.
2. Choose targeted tests for independently bounded changes, add contract/integration coverage for crossed boundaries.
3. Separate fast developer signal from heavier release/soak/security gates when safe.
4. Explicitly list chosen and omitted tests with why, which risks each protects, and expected cost.
5. If existing current evidence suffices and no new test/run is justified, recommend NO_ADDITIONAL_TESTING_NEEDED with the sufficiency argument.

## Required outputs
- selected and omitted suite list
- test costs and confidence
- run plan or sufficiency evidence

## Stop / refuse
- Critical invariant omitted solely because slow
- Release-required suite skipped without explicit authority
- Using tests for a different revision as current proof

## Boundary
Distributed environment needs become requests for Infrae through the composition layer.
