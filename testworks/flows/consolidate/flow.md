---
flow: consolidate
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - consolidate
---
# Consolidate flow

**Purpose.** Prove proposed removals or consolidation preserve distinct regression detection.

## Steps
1. Identify exact behavior/failure signals protected by each candidate, including negatives and incident regressions.
2. Test proposed replacement against original fixtures and representative failure mutations; compare oracles and detection, not only line/branch coverage.
3. Retain mandatory security/safety and critical invariant tests regardless of convenience.
4. Record deletion/merge proposal, reversal strategy and any lost independent signal; unknown equivalence means KEEP.
5. Require controlled repository mutation and post-change qualification via the composition layer.

## Required outputs
- semantic equivalence evidence
- proposed changes only
- risk/rollback plan
- fresh requalification plan

## Stop / refuse
- Auto-deleting tests
- Inferring equivalence from same name or same coverage percentage
- Removing a critical control for speed

## Boundary
Getter must apply any approved repository changes; Gitter supplies revision and ownership truth.
