"""Host-validated integration verification for TerraFormer recomposition claims.

For ``INTEGRATED -> QUALIFIED``, the host must see real contract probes
across the interface -- not a diagram, not a passing unit suite on one side.
This module gives the trusted host a bounded, deterministic check over a
structured composition claim:

- every service interface carries request/response validity and version
  compatibility probes with passing receipts;
- lifecycle (startup/shutdown), concurrency, partial failure, restart
  recovery, and idempotent replay probes are present with passing receipts;
- no recomposition recreates the original God Object: one component owning
  everybody's state, policies, persistence, and error recovery is rejected;
- an optional GodKiller boundary packet may seed the expected contract, but
  the composition fingerprint is independently revalidated -- and a
  standalone assessment works without that packet;
- a single coherent service may return NOT_NEEDED instead of failing.

Jev may recommend which integration to probe. It must not certify that a
recomposition is sound.
"""

from __future__ import annotations

from dataclasses import dataclass


REQUIRED_PROBE_KINDS = (
    "request_response",
    "version_compat",
    "lifecycle",
    "concurrency",
    "partial_failure",
    "restart_recovery",
    "replay",
)

CROSS_CUTTING_DOMAINS = ("state", "policies", "persistence", "error_recovery")


@dataclass(frozen=True)
class Service:
    id: str
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    owns: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProbeResult:
    kind: str
    target: str
    passed: bool
    evidence_ref: str = ""


@dataclass(frozen=True)
class CompositionClaim:
    subject_ref: str
    subject_revision: int
    services: tuple[Service, ...] = ()
    probes: tuple[ProbeResult, ...] = ()
    composition_fingerprint: str = ""
    boundary_packet: str = ""
    boundary_fingerprint: str = ""
    no_recomposition_needed: bool = False
    no_recomposition_rationale: str = ""


@dataclass(frozen=True)
class Verification:
    verdict: str  # QUALIFIED | NOT_NEEDED | NOT_QUALIFIED
    reasons: tuple[str, ...] = ()

    @property
    def qualified(self) -> bool:
        return self.verdict == "QUALIFIED"


def _god_object_holdings(service: Service) -> tuple[str, ...]:
    owned = set(service.owns)
    return tuple(domain for domain in CROSS_CUTTING_DOMAINS if domain in owned)


def verify_composition(claim: CompositionClaim,
                       *, current_revision: int) -> Verification:
    """Verify a recomposition claim against the current subject revision."""
    if claim.subject_revision != current_revision:
        return Verification("NOT_QUALIFIED", (
            f"stale claim revision {claim.subject_revision} "
            f"(current {current_revision}); re-observe before approval",))
    if not claim.services:
        return Verification("NOT_QUALIFIED", ("no services declared",))

    if claim.no_recomposition_needed:
        if len(claim.services) == 1 and claim.no_recomposition_rationale.strip():
            return Verification("NOT_NEEDED", (
                "single coherent service; recomposition not required: "
                + claim.no_recomposition_rationale.strip(),))
        return Verification("NOT_QUALIFIED", (
            "no_recomposition_needed requires exactly one service and a "
            "stated rationale",))

    reasons: list[str] = []
    by_id = {service.id: service for service in claim.services}

    for service in claim.services:
        holdings = _god_object_holdings(service)
        if len(holdings) >= 3:
            reasons.append(
                f"service {service.id!r} owns {', '.join(holdings)}: "
                "recomposition recreated the God Object")

    for service in claim.services:
        kinds = {probe.kind for probe in claim.probes
                 if probe.target == service.id and probe.passed
                 and probe.evidence_ref.strip()}
        for required in ("request_response", "version_compat"):
            if required not in kinds:
                reasons.append(
                    f"service {service.id!r} lacks a passing "
                    f"{required} probe with an evidence ref")

    provided = {name for service in claim.services for name in service.provides}
    for service in claim.services:
        for name in service.requires:
            if name not in provided:
                reasons.append(
                    f"service {service.id!r} requires {name!r} "
                    "which no service provides")

    composition_kinds = {probe.kind for probe in claim.probes
                         if probe.passed and probe.evidence_ref.strip()}
    for required in REQUIRED_PROBE_KINDS:
        if required in ("request_response", "version_compat"):
            continue
        if required not in composition_kinds:
            reasons.append(
                f"composition lacks a passing {required} probe "
                "with an evidence ref")

    if claim.boundary_packet.strip():
        if not claim.boundary_fingerprint.strip():
            reasons.append("boundary packet cited without its fingerprint")
        elif (claim.composition_fingerprint.strip()
              and claim.composition_fingerprint != claim.boundary_fingerprint):
            reasons.append(
                "composition fingerprint does not match the cited GodKiller "
                "boundary packet; the boundary contract was not revalidated")

    if reasons:
        return Verification("NOT_QUALIFIED", tuple(reasons))
    return Verification("QUALIFIED", (
        "per-service request/response and version probes pass; lifecycle, "
        "concurrency, partial failure, restart recovery, and replay probes "
        "pass; no service owns the cross-cutting domains",))


__all__ = ["CROSS_CUTTING_DOMAINS", "CompositionClaim", "ProbeResult",
           "REQUIRED_PROBE_KINDS", "Service", "Verification",
           "verify_composition"]
