---
flow: recover
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - recover
---
# Recover flow

**Purpose.** Deterministically reopen claims when revision, environment, risk or evidence validity changes.

## Steps
1. Mark the invalidated packet historical and record exact cause and earliest affected boundary.
2. Separate independent still-valid receipts from those affected by code, suite, toolchain, environment or workload drift.
3. Re-inventory the changed subject where the previous inventory is no longer trustworthy.
4. Rerun only invalidated tests when isolation is supported; requalify cross-cutting effects at broader scope.
5. Produce a new packet; do not mutate the earlier evidence or claim it was always current.

## Required outputs
- invalidation record
- bounded recovery/reassessment plan
- fresh subject identity

## Stop / refuse
- Silently reusing old receipts
- Replaying prior VERIFIED without matching fingerprints
- Forgetting a contradictory operator report

## Boundary
Request repository truth from Gitter or environment attestation from Infrae through composition as needed.
