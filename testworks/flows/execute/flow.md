---
flow: execute
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - execute
---
# Execute flow

**Purpose.** Obtain trustworthy, reproducible execution receipts for selected work.

## Steps
1. Record exact subject, suite definition, relevant workload and toolchain fingerprints before execution.
2. Execute only the selected tests in the authorized runner; retain precise arguments, seed, environment, exit status and timing.
3. Capture stdout/stderr and immutable artifact/log references with test outcomes.
4. Distinguish not-run, skipped, failed, passed, and interrupted; report incomplete work as INCONCLUSIVE.
5. Recheck subject fingerprint after execution; changed identity invalidates evidence for the prior claim.

## Required outputs
- execution receipts
- test outcomes
- duration/compute cost
- changed-state detection

## Stop / refuse
- Runner authority unknown
- Unpinned or unrecorded subject
- Logging/artifact provenance insufficient for qualification

## Boundary
Actual infrastructure provisioning belongs to Infrae; do not impersonate its environment receipts.
