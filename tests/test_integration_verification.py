"""Consumer-visible integration verification: probes with receipts, not diagrams."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from integration_verification import (  # noqa: E402
    CompositionClaim,
    ProbeResult,
    Service,
    verify_composition,
)


def _probes(targets=("policy", "delivery")):
    results = []
    for target in targets:
        results.append(ProbeResult("request_response", target, True,
                                   f"evidence:rr:{target}"))
        results.append(ProbeResult("version_compat", target, True,
                                   f"evidence:vc:{target}"))
    for kind in ("lifecycle", "concurrency", "partial_failure",
                 "restart_recovery", "replay"):
        results.append(ProbeResult(kind, "composition", True,
                                   f"evidence:{kind}:1"))
    return tuple(results)


def _claim(**overrides):
    params = dict(
        subject_ref="subject:svc",
        subject_revision=7,
        services=(
            Service(id="policy", provides=("decide",), requires=(),
                    owns=("policy-rules",)),
            Service(id="delivery", provides=("send",), requires=("decide",),
                    owns=("outbox",)),
        ),
        probes=_probes(),
        composition_fingerprint="f" * 64,
    )
    params.update(overrides)
    return CompositionClaim(**params)


def test_sound_composition_is_qualified():
    result = verify_composition(_claim(), current_revision=7)
    assert result.verdict == "QUALIFIED" and result.qualified


def test_recreated_god_object_is_rejected():
    claim = _claim(services=(
        Service(id="orchestrator", provides=("everything",), requires=(),
                owns=("state", "policies", "persistence", "error_recovery")),),
        probes=_probes(("orchestrator",)))
    result = verify_composition(claim, current_revision=7)
    assert result.verdict == "NOT_QUALIFIED"
    assert any("God Object" in reason for reason in result.reasons)


def test_missing_version_probe_is_rejected():
    probes = tuple(probe for probe in _probes()
                   if not (probe.kind == "version_compat"
                           and probe.target == "delivery"))
    result = verify_composition(_claim(probes=probes), current_revision=7)
    assert result.verdict == "NOT_QUALIFIED"
    assert any("delivery" in reason and "version_compat" in reason
               for reason in result.reasons)


def test_missing_replay_probe_is_rejected():
    probes = tuple(probe for probe in _probes() if probe.kind != "replay")
    result = verify_composition(_claim(probes=probes), current_revision=7)
    assert result.verdict == "NOT_QUALIFIED"
    assert any("replay" in reason for reason in result.reasons)


def test_unmet_requirement_is_rejected():
    claim = _claim(services=(
        Service(id="delivery", provides=("send",), requires=("decide",),
                owns=("outbox",)),))
    result = verify_composition(claim, current_revision=7)
    assert result.verdict == "NOT_QUALIFIED"
    assert any("decide" in reason for reason in result.reasons)


def test_standalone_assessment_works_without_boundary_packet():
    result = verify_composition(_claim(), current_revision=7)
    assert result.verdict == "QUALIFIED"


def test_mismatched_boundary_fingerprint_is_rejected():
    claim = _claim(boundary_packet="packet:gk:1",
                   boundary_fingerprint="b" * 64,
                   composition_fingerprint="c" * 64)
    result = verify_composition(claim, current_revision=7)
    assert result.verdict == "NOT_QUALIFIED"
    assert any("fingerprint" in reason for reason in result.reasons)


def test_matching_boundary_packet_passes():
    claim = _claim(boundary_packet="packet:gk:1",
                   boundary_fingerprint="f" * 64,
                   composition_fingerprint="f" * 64)
    assert verify_composition(claim, current_revision=7).verdict == "QUALIFIED"


def test_single_coherent_service_needs_nothing():
    claim = _claim(
        services=(Service(id="svc", provides=("run",), requires=(),
                           owns=("ledger",)),),
        probes=(),
        no_recomposition_needed=True,
        no_recomposition_rationale="one coherent owner; no interface to probe")
    result = verify_composition(claim, current_revision=7)
    assert result.verdict == "NOT_NEEDED"


def test_stale_revision_is_rejected():
    result = verify_composition(_claim(), current_revision=8)
    assert result.verdict == "NOT_QUALIFIED"
    assert "stale" in result.reasons[0]
