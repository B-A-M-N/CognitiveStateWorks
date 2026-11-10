"""Host-validated test assurance for TestWorks qualification.

The reference ``testworks/qualification/policy.py`` is explicitly a scenario
reference, not the trusted runtime validator. This module is the host-side
counterpart the authority consults before it accepts a TestWorks outcome:

- exact subject fingerprints on every execution receipt (a green run from
  another subject proves nothing about this one);
- runner and environment identity on every receipt;
- independent execution receipts for each required test, all passing;
- required risk coverage where each required test's oracle actually names
  the invariant it protects;
- the VERIFIED versus NO_ADDITIONAL_TESTING_NEEDED distinction: the latter
  means the current evidence justifies no further testing for a scoped
  decision, not that every test passed or every risk is covered;
- test deletion is never authorized by a proposal alone: critical-invariant
  and unique-regression tests are never removable, and anything else needs
  host-owned authorization plus proven equivalence, preserved detection,
  rollback, and a planned requalification.

Jev can prioritize testing alternatives and recommend stronger oracles. It
cannot manufacture an execution receipt, override a required critical gate,
or authorize test deletion.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExecutionReceipt:
    test_id: str
    subject_fingerprint: str
    runner_id: str
    environment_id: str
    result: str  # PASS | FAIL
    protects_invariant: str = ""


@dataclass(frozen=True)
class AssuranceClaim:
    subject_ref: str
    subject_fingerprint: str
    subject_revision: int
    required_tests: tuple[str, ...] = ()
    required_risks: tuple[str, ...] = ()
    receipts: tuple[ExecutionReceipt, ...] = ()
    expected_runner_id: str = ""
    expected_environment_id: str = ""
    requirements_met: bool = False
    risk_justified: bool = False
    receipts_fresh: bool = False
    mandatory_release_gate_due: bool = False
    scoped_no_further_testing: bool = False


@dataclass(frozen=True)
class Assurance:
    verdict: str  # VERIFIED | NO_ADDITIONAL_TESTING_NEEDED | INCONCLUSIVE | INVALIDATED
    reasons: tuple[str, ...] = ()

    @property
    def verified(self) -> bool:
        return self.verdict == "VERIFIED"


@dataclass(frozen=True)
class RemovalProposal:
    test_id: str
    classification: str = ""
    owner_authorized: bool = False
    semantic_equivalence_proven: bool = False
    regression_detection_preserved: bool = False
    rollback_available: bool = False
    post_change_qualification_planned: bool = False


def assess_assurance(claim: AssuranceClaim, *, current_revision: int) -> Assurance:
    """Assess a test-assurance claim against the current subject revision."""
    if claim.subject_revision != current_revision:
        return Assurance("INVALIDATED", (
            f"stale claim revision {claim.subject_revision} "
            f"(current {current_revision}); re-observe before approval",))
    if not claim.subject_fingerprint.strip():
        return Assurance("INVALIDATED", ("no subject fingerprint declared",))

    foreign = sorted({receipt.test_id for receipt in claim.receipts
                      if receipt.subject_fingerprint != claim.subject_fingerprint})
    if foreign:
        return Assurance("INVALIDATED", (
            "receipts from another subject prove nothing here: "
            + ", ".join(foreign),))

    if claim.expected_runner_id.strip():
        rogue = sorted({receipt.runner_id for receipt in claim.receipts
                        if receipt.runner_id != claim.expected_runner_id})
        if rogue:
            return Assurance("INCONCLUSIVE", (
                "unrecognized runner identity: " + ", ".join(rogue),))
    if claim.expected_environment_id.strip():
        rogue = sorted({receipt.environment_id for receipt in claim.receipts
                        if receipt.environment_id != claim.expected_environment_id})
        if rogue:
            return Assurance("INCONCLUSIVE", (
                "unrecognized environment identity: " + ", ".join(rogue),))

    if claim.scoped_no_further_testing and not claim.required_tests:
        if claim.mandatory_release_gate_due:
            return Assurance("INCONCLUSIVE",
                             ("mandatory release gate is due; run it",))
        if claim.requirements_met and claim.risk_justified and claim.receipts_fresh:
            return Assurance("NO_ADDITIONAL_TESTING_NEEDED", (
                "current evidence justifies no further testing for this "
                "scoped decision; this is not a claim that every test "
                "passed or every risk is covered",))
        return Assurance("INCONCLUSIVE", (
            "scoped no-further-testing needs met requirements, justified "
            "risk, and fresh receipts",))

    if not claim.required_tests:
        return Assurance("INCONCLUSIVE", ("no required tests declared",))

    by_test = {receipt.test_id: receipt for receipt in claim.receipts}
    missing = [name for name in claim.required_tests if name not in by_test]
    if missing:
        return Assurance("INCONCLUSIVE",
                         ("missing execution receipts: " + ", ".join(missing),))
    failed = [name for name in claim.required_tests
              if by_test[name].result != "PASS"]
    if failed:
        return Assurance("INCONCLUSIVE",
                         ("required tests not passing: " + ", ".join(failed),))
    oracles = [name for name in claim.required_tests
               if not by_test[name].protects_invariant.strip()]
    if oracles:
        return Assurance("INCONCLUSIVE", (
            "oracles do not name the invariant they protect: "
            + ", ".join(oracles),))
    if claim.required_risks:
        covered = {by_test[name].protects_invariant for name in claim.required_tests}
        uncovered = [risk for risk in claim.required_risks if risk not in covered]
        if uncovered:
            return Assurance("INCONCLUSIVE", (
                "required risks without a protecting oracle: "
                + ", ".join(uncovered),))
    if not claim.requirements_met:
        return Assurance("INCONCLUSIVE", ("requirements not met",))
    return Assurance("VERIFIED", (
        "exact subject fingerprints; recognized runner and environment; "
        "independent passing receipts for every required test; every "
        "required risk covered by a named oracle",))


def assess_removal(proposal: RemovalProposal) -> Assurance:
    """Decide whether a test-deletion proposal is even eligible.

    Never permission to mutate: the host owns the mutation path. A proposal
    alone -- Jev or otherwise -- authorizes nothing.
    """
    if proposal.classification in {"CRITICAL_INVARIANT", "UNIQUE_REGRESSION"}:
        return Assurance("INCONCLUSIVE", (
            f"{proposal.test_id} protects a "
            f"{proposal.classification.lower().replace('_', ' ')}; "
            "deletion is not eligible",))
    missing = [name for name in (
        "owner_authorized", "semantic_equivalence_proven",
        "regression_detection_preserved", "rollback_available",
        "post_change_qualification_planned")
        if not getattr(proposal, name)]
    if missing:
        return Assurance("INCONCLUSIVE", (
            f"{proposal.test_id} deletion lacks: " + ", ".join(missing),))
    return Assurance("VERIFIED", (
        f"{proposal.test_id} deletion is eligible; the host still owns "
        "the mutation and the requalification",))


__all__ = ["Assurance", "AssuranceClaim", "ExecutionReceipt",
           "RemovalProposal", "assess_assurance", "assess_removal"]
