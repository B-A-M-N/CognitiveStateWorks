# TestWorks — Runtime Capsule

Proportionate test-assurance discipline. Inventories change surface and
existing evidence, strategizes by risk, runs only selected suites, evaluates
receipts bound to the exact subject fingerprint, and qualifies or
concludes NO_ADDITIONAL_TESTING_NEEDED. Never rewards test volume.

## State vocabulary

- UNASSESSED → INVENTORIED
- INVENTORIED → STRATEGIZED
- STRATEGIZED → EXECUTING
- EXECUTING → EVALUATED
- EVALUATED → VERIFIED
- STRATEGIZED → NO_ADDITIONAL_TESTING_NEEDED
- EVALUATED → INCONCLUSIVE
- EXECUTING → INCONCLUSIVE
- STRATEGIZED → INCONCLUSIVE
- INVALIDATED → UNASSESSED
- BLOCKED → UNASSESSED
- INCONCLUSIVE → STRATEGIZED

Use only states and transitions declared in transitions.yaml. The runtime
resolver pins that contract; this capsule does not define a second state
machine.

## Hard gates

- Establish subject identity (revision, dirty tree, test definitions,
  environment, workload) before strategizing; unknown facts stay unknown.
- Consequential execution and qualification require host authorization on
  the current subject fingerprint; stale receipts never qualify a new
  revision.
- VERIFIED requires attested, passing, subject-matched receipts for every
  required test plus explicit omissions and residual risk. A planned run is
  never marked executed; a rerun pass never rewrites a prior failure.
- Consolidation is a proposal only: TestWorks never mutates repositories.
  Getter applies approved changes after ownership, semantic equivalence,
  and rollback are established.

## Exit produced

Emit `testing_evidence_packet` under the canonical CSW envelope with exact
subject fingerprint, selected and omitted suites, results, evidence
quality, risk, residual risk, and unknowns.

## Completion

Done when VERIFIED or NO_ADDITIONAL_TESTING_NEEDED is evidence-backed for
the stated subject fingerprint and scope. Both invalidate on any material
change to subject, definitions, environment, or risk scope.
