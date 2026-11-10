---
flow: qualify
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - qualify
---
# Qualify flow

**Purpose.** Establish whether actual executed assurance is sufficient for the exact subject and declared scope.

## Steps
1. Reconfirm revision, relevant dirty-tree, suite and environment fingerprints and claimed workload at decision time.
2. Check required coverage, oracle trust, absence of unaccounted critical gaps and honest treatment of skips/flakes.
3. Separate construction evidence from behavioral outcomes. Ensure failures are resolved with a new valid receipt, not silently discarded.
4. Record selected/omitted tests, uncovered risks, scope limits and host attestation before VERIFIED.
5. If current evidence already suffices and no further work is needed before execution, use the distinct sufficiency transition; never pretend a run occurred.

## Required outputs
- qualification or sufficiency guard evidence
- testing_evidence_packet
- explicit residual risks and conditions

## Stop / refuse
- Green from another subject
- Untrusted execution claims
- Any unresolved required failing gate
- Critical omitted gate without approved scope exception

## Boundary
Release and deployment decisions remain with downstream authorized owners.
