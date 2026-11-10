---
flow: diagnose
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - diagnose
---
# Diagnose flow

**Purpose.** Differentiate product bugs, bad tests, flaky behavior and environmental failures.

## Steps
1. Classify by evidence: product regression, test defect, infrastructure, environment, nondeterminism, or UNKNOWN.
2. Inspect reproducible conditions: seed, schedule, timing, workers, fixture isolation, dependency versions and resources.
3. Use minimal controlled reruns with reason, cap and changing variables recorded; rerun success does not erase prior failure.
4. Propose isolated repairs or quarantine only with explicit exposure, alternate detection and an expiry/review condition.
5. Revise selection/qualification if a gate has lost reliability; do not report green via retry masking.

## Required outputs
- root cause hypothesis and confidence
- proof or counterevidence
- repair/retention proposal
- residual risk

## Stop / refuse
- Automatically rerunning until green
- Calling a failure flaky without evidence
- Quarantining critical invariant with no compensating gate

## Boundary
Repository test repair through Getter; external runner faults via Infrae.
