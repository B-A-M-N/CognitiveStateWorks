"""Host-validated decomposition assessment: real structural checks, not theater."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from architecture_assessment import (  # noqa: E402
    Component,
    DecompositionClaim,
    Dependency,
    SharedMutableState,
    assess_decomposition,
)


def _claim(**overrides):
    params = dict(
        subject_ref="subject:svc",
        subject_revision=7,
        components=(
            Component(id="policy", responsibilities=("policy",),
                      owns_state=("policy-rules",),
                      provides=("decide",), requires=()),
            Component(id="delivery", responsibilities=("delivery",),
                      owns_state=("outbox",),
                      provides=("send",), requires=("decide",)),
        ),
        dependencies=(Dependency("delivery", "policy"),),
        shared_mutable=(),
        coordination_contracts=(),
        interface_preserved=True,
        regression_evidence_refs=("evidence:regression:1",),
    )
    params.update(overrides)
    return DecompositionClaim(**params)


def test_clean_partition_is_approved():
    result = assess_decomposition(_claim(), current_revision=7)
    assert result.verdict == "APPROVED" and result.approved


def test_cosmetic_split_with_shared_writers_is_rejected():
    claim = _claim(shared_mutable=(
        SharedMutableState(name="context", writers=("policy", "delivery"),
                           readers=("delivery",)),))
    result = assess_decomposition(claim, current_revision=7)
    assert result.verdict == "REJECTED"
    assert any("context" in reason for reason in result.reasons)


def test_centralized_authority_needs_no_decomposition():
    claim = _claim(
        components=(Component(id="coordinator",
                              responsibilities=("invariant",),
                              owns_state=("ledger",),
                              provides=("guard",), requires=()),),
        dependencies=())
    result = assess_decomposition(claim, current_revision=7)
    assert result.verdict == "NO_DECOMPOSITION_NEEDED"


def test_dual_ownership_is_rejected():
    claim = _claim(components=(
        Component(id="a", responsibilities=("policy",),
                  provides=("decide",), requires=()),
        Component(id="b", responsibilities=("policy",),
                  provides=("send",), requires=("decide",))))
    result = assess_decomposition(claim, current_revision=7)
    assert result.verdict == "REJECTED"
    assert any("exactly one owner" in reason for reason in result.reasons)


def test_cycle_is_rejected():
    claim = _claim(dependencies=(Dependency("delivery", "policy"),
                                 Dependency("policy", "delivery")))
    result = assess_decomposition(claim, current_revision=7)
    assert result.verdict == "REJECTED"
    assert any("circular" in reason for reason in result.reasons)


def test_missing_regression_evidence_is_rejected():
    claim = _claim(regression_evidence_refs=(), interface_preserved=True)
    result = assess_decomposition(claim, current_revision=7)
    assert result.verdict == "REJECTED"


def test_stale_revision_is_rejected():
    result = assess_decomposition(_claim(), current_revision=8)
    assert result.verdict == "REJECTED"
    assert "stale" in result.reasons[0]


def test_coordinated_shared_state_can_pass():
    claim = _claim(shared_mutable=(
        SharedMutableState(name="ledger", writers=("policy",),
                           readers=("policy", "delivery")),),
        coordination_contracts=("ledger",))
    result = assess_decomposition(claim, current_revision=7)
    assert result.verdict == "APPROVED"
