"""Enforcing standalone controller for one durable StateWork subject."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Optional

if __package__:
    from .errors import TransitionError
    from .evidence import EvidenceStore
    from .resources import _aware_datetime
    from .state_store import SubjectStateStore
    from .transition_engine import TransitionDecision, TransitionEngine
else:
    from errors import TransitionError
    from evidence import EvidenceStore
    from resources import _aware_datetime
    from state_store import SubjectStateStore
    from transition_engine import TransitionDecision, TransitionEngine

class StandaloneStateWorkController:
    """Enforcing CSW-only host controller for one durable subject identity.

    The controller, not the caller, owns the current state. Every request
    atomically checks the expected revision, resolves trusted evidence, checks
    the matching transition edge, and commits history. A conflict requires
    reload/reinspection; it never overwrites newer state.
    """
    def __init__(self, *, contract: Mapping[str, Any], identity: Mapping[str, Any],
                 state_store: SubjectStateStore, evidence_store: EvidenceStore,
                 evidence_registry: Optional[Mapping[str, Any]] = None):
        self.identity = dict(identity)
        self.state_store = state_store
        self.evidence_store = evidence_store
        self.engine = TransitionEngine(dict(contract), evidence_registry=evidence_registry,
                                       require_registered=True, evidence_store=evidence_store)
        initial = contract.get("initial_state")
        if not isinstance(initial, str) or not initial:
            raise TransitionError("standalone StateWork contract requires initial_state")
        snapshot = state_store.get(identity)
        if snapshot.get("state") is None:
            try:
                state_store.commit(identity, expected_revision=0, new_state=initial,
                                   transition={"trigger": "controller_initialization",
                                               "to_state": initial})
            except TransitionError as exc:
                if "revision conflict" not in str(exc):
                    raise
                snapshot = state_store.get(identity)
                if snapshot.get("state") is None:
                    raise
        current = state_store.get(identity)

    def inspect(self) -> Dict[str, Any]:
        return self.state_store.get(self.identity)

    def request_transition(self, *, to_state: str, trigger: str,
                           evidence_refs: Iterable[str], expected_revision: int) -> TransitionDecision:
        snapshot = self.inspect()
        if int(snapshot.get("revision", 0)) != int(expected_revision):
            raise TransitionError(
                f"subject state revision conflict: expected {expected_revision}, "
                f"found {snapshot.get('revision', 0)}; re-inspect required")
        from_state = str(snapshot.get("state"))
        references = list(evidence_refs)
        resolved = self.evidence_store.resolve(references)
        edges = self.engine.matching_edges(from_state, to_state, trigger)
        freshness = (edges[0].get("evidence_freshness") if len(edges) == 1 else {}) or {}
        entry = snapshot.get("updated_at")
        required_kinds = set(edges[0].get("required_evidence") or []) if len(edges) == 1 else set()
        relevant = [item for item in resolved if item.get("kind") in required_kinds]
        if freshness.get("mode") == "after_state_entry" and entry:
            try:
                entry_at = _aware_datetime(entry)
                for item in relevant:
                    if _aware_datetime(item.get("observed_at")) < entry_at:
                        return TransitionDecision(
                            False, "evidence predates current state entry", from_state,
                            to_state, trigger, list(edges[0].get("required_evidence", [])))
            except ValueError as exc:
                return TransitionDecision(False, str(exc), from_state, to_state, trigger)
        max_age = freshness.get("max_age_seconds")
        if max_age is not None:
            now = datetime.now(timezone.utc)
            for item in relevant:
                try:
                    observed = _aware_datetime(item.get("observed_at"))
                except ValueError as exc:
                    return TransitionDecision(False, str(exc), from_state, to_state, trigger)
                if (now - observed).total_seconds() > int(max_age):
                    return TransitionDecision(False, "evidence exceeds declared freshness", from_state, to_state, trigger)
        decision = self.engine.transition(
            str(self.identity["subject_ref"]), from_state, to_state,
            trigger=trigger, evidence_refs=resolved)
        if not decision.allowed:
            return decision
        transition_record = {"trigger": trigger, "evidence_refs": references,
                             "decision_reason": decision.reason,
                             "progress": decision.progress_facts()}
        self.state_store.commit(
            self.identity, expected_revision=expected_revision, new_state=to_state,
            transition=transition_record)
        return decision
