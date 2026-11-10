---
name: testworks
description: >
  Test assurance StateWork. Use to decide whether more testing is warranted,
  design defensible oracles and regression cases, select proportionate suites,
  inspect execution receipts, diagnose failures and flakes, assess test portfolio
  value, propose safe consolidation, qualify subject-bound evidence, and recover
  invalidated test claims. Explicitly supports NO_ADDITIONAL_TESTING_NEEDED.
---
# TestWorks — Proportionate Test Assurance

**Mission:** maximize defensible assurance per unit of testing effort, not test count.

## Activation and ownership
Own testing requirements, risk-based test design, suite choice, interpretation,
portfolio value, qualification evidence, and invalidation. Do **not** own source
control truth or mutation, test infrastructure provisioning, environment authority,
product architecture, or the host's transition engine. Read-only analysis is the
default. Never claim a test ran unless a trustworthy receipt proves it did.

## State discipline
Read `transitions.yaml`. Track the actual subject state, not the agent's claimed
progress. Distinguish the **workflow state** from risk class and test confidence.
Use only declared transitions. Evidence is mandatory for a consequential transition.
`VERIFIED` and `NO_ADDITIONAL_TESTING_NEEDED` are terminal for the *specified*
subject fingerprint and scope, never blanket project-wide endorsements.

## First action: triage
Determine the change's behavioral surface, affected interfaces and invariants,
prior incidents, release use case, already-present tests and receipts, test execution
cost, and which facts are unknown. Establish subject identity (revision, dirty-tree
content if any, environment, test definitions, relevant workload). Unknown critical
facts do not silently become evidence.

## Core decision rules
1. **Do not generate tests by reflex.** Write the gap hypothesis, protected behavior,
   failure mode, oracle, and why existing cases would not detect it first.
2. **Do not demand a full suite by reflex.** Select by changed risk surface and
   confidence, not a predetermined volume quota. Retain mandatory release/security
   invariants and independent critical qualification gates.
3. **Do not optimize by hiding failure.** Treat flaky, quarantined, skipped, and
   unexecuted tests as qualified omissions with residual risk, not passing tests.
4. **Do not delete tests automatically.** Produce a bounded consolidation proposal;
   ask the repository-mutation owner to apply any change after ownership, semantic
   equivalence, and rollback are established.
5. **Do not overstate evidence.** A successful command is not a correct application.
   A suite that passed for a different SHA, dirty-tree fingerprint, dependency set,
   environment, test definition, or workload is not current qualification.
6. **Conclude NO_ADDITIONAL_TESTING_NEEDED when warranted.** A recorded sufficiency
   argument must identify protected risks, fresh evidence, omitted cases, and limits.
   It does not say no risk remains or that all existing tests were run.

## Flow routing
Choose exactly one immediate flow by intended output, not keyword similarity.
The internal flows are `triage`, `design`, `generate`, `select`, `execute`,
`diagnose`, `audit`, `consolidate`, `qualify`, and `recover`. See `flows/README.md`.
Flows do not invoke one another as tools. The StateWork transition contract and
composition layer decide the next action. A cross-domain need emits a packet or
handoff recommendation; it never directly invokes Gitter, Getter, Infrae,
GodKiller, or TerraFormer.

## Guardrails for evidence and authority
- Every trusted execution receipt binds command/suite, exact subject fingerprint,
  environment fingerprint, test definitions, workload parameters where relevant,
  observed time, exit and outcome, and durable logs/artifacts.
- Test generation or consolidation may recommend repository edits, but TestWorks
  must not perform uncontrolled mutations under someone else's ownership.
- The published generic host observation issuer is a **provenance plumbing hook**,
  not proof that receipt verification, equivalence checks or scope sufficiency are
  already implemented. The host must validate semantic content independently.
- Never mark a planned run as executed. Never mark a rerun passing as proof that
  the previous failure was a flake. Classify cause or retain the uncertainty.

## Outputs
Emit `testing_evidence_packet` using the canonical CSW envelope and domain payload
schema in `contracts/schemas/`. Include exact subject identity, selection (chosen
and omitted), results, evidence quality, risk, residual risk, and recommended next
transition. Maintain inspectable references to source receipts. Missing facts go in
`unknowns` and unresolved stop conditions in `blockers`.

## Completion
**VERIFIED:** scoped risk and required gates covered; test results are trustworthy,
passing, and current; omissions and residual risk explicit; host attests the guard.
**NO_ADDITIONAL_TESTING_NEEDED:** no *additional* run or test generation is justified
for this scoped decision; existing valid evidence supports that conclusion.
Both invalidate on any material change to their claimed subject/scope or when
contradictory evidence appears. `INCONCLUSIVE` and `BLOCKED` are not successes.
