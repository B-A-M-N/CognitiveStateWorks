"""Reference-only, deterministic TestWorks decisions.

This module is NOT a trusted host transition/evidence validator. It demonstrates
key guard behavior for qualification scenarios and must not be used to mint
host evidence or authorize repository changes.
"""
from __future__ import annotations


def before_execution(case: dict) -> str:
    """Return the justified next *recommendation*, not an authoritative state."""
    if not case.get("subject_known") or not case.get("scope_known"):
        return "BLOCKED"
    if not case.get("fingerprints_match", True):
        return "INVALIDATED"
    if case.get("unprotected_critical_invariant") or case.get("coverage_gap"):
        return "ADD_COVERAGE"
    if case.get("required_failure_unresolved") or case.get("flaky_required_gate"):
        return "INCONCLUSIVE"
    if not case.get("receipts_fresh", False):
        return "RUN_SELECTED"
    if case.get("mandatory_release_gate_due", False):
        return "RUN_SELECTED"
    if case.get("requirements_met", False) and case.get("risk_justified", False):
        return "NO_ADDITIONAL_TESTING_NEEDED"
    return "RUN_SELECTED"


def after_execution(case: dict) -> str:
    """Cannot qualify without subject-matched, attested, passing required tests."""
    if not case.get("fingerprints_match", False):
        return "INVALIDATED"
    if not case.get("host_attested") or not case.get("receipts_fresh"):
        return "INCONCLUSIVE"
    if not case.get("required_tests"):
        return "INCONCLUSIVE"
    results = case.get("results", {})
    if any(results.get(t) != "PASS" for t in case["required_tests"]):
        return "INCONCLUSIVE"
    if case.get("unprotected_critical_invariant") or case.get("coverage_gap"):
        return "INCONCLUSIVE"
    return "QUALIFIED" if case.get("requirements_met") else "INCONCLUSIVE"


def removal_permitted(case: dict) -> bool:
    """Conservative eligibility for a proposal, never permission to mutate."""
    if case.get("classification") in {"CRITICAL_INVARIANT", "UNIQUE_REGRESSION"}:
        return False
    return bool(
        case.get("owner_authorized")
        and case.get("semantic_equivalence_proven")
        and case.get("regression_detection_preserved")
        and case.get("rollback_available")
        and case.get("post_change_qualification_planned")
    )
