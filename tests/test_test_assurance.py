"""Host-validated test assurance: receipts, identity, oracles, deletion gates."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from test_assurance import (  # noqa: E402
    AssuranceClaim,
    ExecutionReceipt,
    RemovalProposal,
    assess_assurance,
    assess_removal,
)


def _receipt(test_id, **overrides):
    params = dict(test_id=test_id, subject_fingerprint="fp:1",
                  runner_id="runner:host:1", environment_id="env:ci:1",
                  result="PASS", protects_invariant=f"invariant:{test_id}")
    params.update(overrides)
    return ExecutionReceipt(**params)


def _claim(**overrides):
    params = dict(
        subject_ref="subject:svc", subject_fingerprint="fp:1",
        subject_revision=7, required_tests=("t-risk", "t-gate"),
        required_risks=("invariant:t-risk",),
        receipts=(_receipt("t-risk"), _receipt("t-gate")),
        expected_runner_id="runner:host:1",
        expected_environment_id="env:ci:1",
        requirements_met=True, risk_justified=True, receipts_fresh=True,
    )
    params.update(overrides)
    return AssuranceClaim(**params)


def test_fully_evidenced_claim_is_verified():
    result = assess_assurance(_claim(), current_revision=7)
    assert result.verdict == "VERIFIED" and result.verified


def test_receipt_from_another_subject_invalidates():
    claim = _claim(receipts=(
        _receipt("t-risk", subject_fingerprint="fp:other"),
        _receipt("t-gate")))
    result = assess_assurance(claim, current_revision=7)
    assert result.verdict == "INVALIDATED"
    assert any("another subject" in reason for reason in result.reasons)


def test_unknown_runner_is_inconclusive():
    claim = _claim(receipts=(
        _receipt("t-risk", runner_id="runner:rogue"),
        _receipt("t-gate")))
    result = assess_assurance(claim, current_revision=7)
    assert result.verdict == "INCONCLUSIVE"


def test_failing_required_test_is_inconclusive():
    claim = _claim(receipts=(
        _receipt("t-risk", result="FAIL"), _receipt("t-gate")))
    result = assess_assurance(claim, current_revision=7)
    assert result.verdict == "INCONCLUSIVE"


def test_oracle_without_named_invariant_is_inconclusive():
    claim = _claim(receipts=(
        _receipt("t-risk", protects_invariant=""), _receipt("t-gate")))
    result = assess_assurance(claim, current_revision=7)
    assert result.verdict == "INCONCLUSIVE"


def test_uncovered_required_risk_is_inconclusive():
    claim = _claim(required_risks=("invariant:t-risk", "invariant:missing"))
    result = assess_assurance(claim, current_revision=7)
    assert result.verdict == "INCONCLUSIVE"
    assert any("invariant:missing" in reason for reason in result.reasons)


def test_scoped_decision_needs_no_further_testing():
    claim = _claim(required_tests=(), required_risks=(), receipts=(),
                   scoped_no_further_testing=True)
    result = assess_assurance(claim, current_revision=7)
    assert result.verdict == "NO_ADDITIONAL_TESTING_NEEDED"


def test_scoped_decision_does_not_mean_everything_passed():
    claim = _claim(required_tests=(), receipts=(),
                   scoped_no_further_testing=True, requirements_met=False)
    result = assess_assurance(claim, current_revision=7)
    assert result.verdict == "INCONCLUSIVE"


def test_mandatory_gate_due_forces_a_run():
    claim = _claim(required_tests=(), receipts=(),
                   scoped_no_further_testing=True,
                   mandatory_release_gate_due=True)
    result = assess_assurance(claim, current_revision=7)
    assert result.verdict == "INCONCLUSIVE"


def test_critical_invariant_deletion_is_not_eligible():
    proposal = RemovalProposal(test_id="t-core",
                               classification="CRITICAL_INVARIANT",
                               owner_authorized=True,
                               semantic_equivalence_proven=True,
                               regression_detection_preserved=True,
                               rollback_available=True,
                               post_change_qualification_planned=True)
    result = assess_removal(proposal)
    assert result.verdict == "INCONCLUSIVE"


def test_redundant_deletion_needs_every_safeguard():
    proposal = RemovalProposal(test_id="t-dup", owner_authorized=True,
                               semantic_equivalence_proven=True,
                               regression_detection_preserved=True,
                               rollback_available=False,
                               post_change_qualification_planned=True)
    assert assess_removal(proposal).verdict == "INCONCLUSIVE"
    full = RemovalProposal(test_id="t-dup", owner_authorized=True,
                           semantic_equivalence_proven=True,
                           regression_detection_preserved=True,
                           rollback_available=True,
                           post_change_qualification_planned=True)
    assert assess_removal(full).verdict == "VERIFIED"


def test_stale_revision_invalidates():
    result = assess_assurance(_claim(), current_revision=8)
    assert result.verdict == "INVALIDATED"
