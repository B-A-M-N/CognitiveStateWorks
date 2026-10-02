"""Evaluate StateWork transition legality and evidence requirements."""
from __future__ import annotations

from dataclasses import dataclass, field
import jsonschema
from typing import Any, Dict, Iterable, List, Mapping, Optional

if __package__:
    from .errors import TransitionError
    from .evidence import EvidenceStore
    from .resources import load_evidence_kind_registry
else:
    from errors import TransitionError
    from evidence import EvidenceStore
    from resources import load_evidence_kind_registry

PROGRESS_CLASSES = {
    "FORWARD_PROGRESS", "LATERAL", "RECOVERY", "INVALIDATION", "REGRESSION",
    "TERMINAL",
}


@dataclass(frozen=True)
class TransitionDecision:
    allowed: bool
    reason: str
    from_state: str
    to_state: str
    trigger: Optional[str] = None
    required_evidence: List[str] = field(default_factory=list)
    evidence_freshness: Dict[str, Any] = field(default_factory=dict)
    # Progress metadata. CFW uses this to distinguish real forward progress
    # from a recovery cycle that merely moved the state machine, so a
    # recovery hop does not silently reset the task's no-progress budget.
    edge_id: Optional[str] = None
    path_class: Optional[str] = None
    progress_class: str = "LATERAL"
    work_class: Optional[str] = None
    domain_effect: Optional[str] = None
    normal_path_rank_before: Optional[int] = None
    normal_path_rank_after: Optional[int] = None

    def progress_facts(self) -> Dict[str, Any]:
        return {"edge_id": self.edge_id, "path_class": self.path_class,
                "progress_class": self.progress_class,
                "work_class": self.work_class, "domain_effect": self.domain_effect,
                "normal_path_rank_before": self.normal_path_rank_before,
                "normal_path_rank_after": self.normal_path_rank_after}

    def is_forward_progress(self) -> bool:
        return self.progress_class in {"FORWARD_PROGRESS", "TERMINAL"}

class TransitionEngine:
    """Machine-readable legality and evidence guards for a StateWork."""

    def __init__(self, contract: Dict[str, Any], *, evidence_registry: Optional[Mapping[str, Any]] = None,
                 require_registered: bool = False, evidence_store: Optional[EvidenceStore] = None) -> None:
        states = contract.get("states")
        transitions = contract.get("transitions")
        if not isinstance(states, list) or not states:
            raise TransitionError("transition contract requires states")
        initial_state = contract.get("initial_state")
        if initial_state is not None and initial_state not in states:
            raise TransitionError("transition contract initial_state is not declared")
        if not isinstance(transitions, list):
            raise TransitionError("transition contract requires transitions")
        if initial_state is None:
            raise TransitionError("transition contract requires initial_state")
        self.states = set(states)
        self.transitions = transitions
        self.completion_states = set(contract.get("completion_states") or [])
        self.normal_path = list(contract.get("normal_path") or [])
        self._normal_rank = {state: index for index, state in enumerate(self.normal_path)}
        registry = evidence_registry
        if registry is None:
            try:
                registry = load_evidence_kind_registry()
            except (FileNotFoundError, ValueError, jsonschema.ValidationError):
                registry = {"kinds": {}}
        self.evidence_registry = dict((registry or {}).get("kinds") or {})
        self.require_registered = require_registered
        self.evidence_store = evidence_store
        edge_ids: set[str] = set()
        for edge in transitions:
            edge_id = edge.get("id")
            if not isinstance(edge_id, str) or not edge_id.strip() or len(edge_id) > 128:
                raise TransitionError("every transition requires a stable bounded id")
            if edge_id in edge_ids:
                raise TransitionError(f"duplicate transition id {edge_id!r}")
            edge_ids.add(edge_id)
            origin = edge.get("from")
            destination = edge.get("to")
            if origin != "*" and origin not in self.states:
                raise TransitionError(f"transition origin {origin!r} is not declared")
            if destination not in self.states:
                raise TransitionError(f"transition destination {destination!r} is not declared")
            if not edge.get("trigger"):
                raise TransitionError(f"transition {origin!r} -> {destination!r} requires a trigger")
            required = edge.get("required_evidence") or []
            if not required or any(not isinstance(kind, str) or not kind for kind in required):
                raise TransitionError(f"transition {origin!r} -> {destination!r} requires evidence kinds")
            if (not edge.get("work_class") or not edge.get("domain_effect")
                    or edge.get("progress_class") not in PROGRESS_CLASSES):
                raise TransitionError(
                    f"transition {edge_id!r} requires work_class, domain_effect, and progress_class")
            path_class = edge.get("path_class")
            if path_class is not None and path_class not in {
                    "normal", "recovery", "failure", "invalidation", "external"}:
                raise TransitionError(f"transition {edge_id!r} has an unsupported path_class")
            if edge.get("path_class") == "external" and edge.get("progress_class") != "INVALIDATION":
                raise TransitionError("external transitions must classify progress as INVALIDATION")
            if (path_class in {"failure", "invalidation"}
                    and edge.get("progress_class") not in {"INVALIDATION", "TERMINAL"}):
                raise TransitionError(
                    "failure and invalidation paths must classify progress as INVALIDATION unless terminal")
            if path_class == "recovery" and edge.get("progress_class") not in {"RECOVERY", "TERMINAL"}:
                raise TransitionError("recovery paths must classify progress as RECOVERY or TERMINAL")
            entering_completion = destination in self.completion_states
            if entering_completion != (edge.get("progress_class") == "TERMINAL"):
                raise TransitionError(
                    f"transition {edge_id!r} must classify completion-state entry as TERMINAL")
            if require_registered and self._is_consequential(edge, str(destination)):
                missing = [kind for kind in required if kind not in self.evidence_registry]
                if missing:
                    raise TransitionError(
                        f"consequential transition {edge_id!r} uses unregistered evidence kinds: {missing}")

    def _progress_facts(self, edge: Mapping[str, Any], from_state: str,
                        to_state: str) -> Dict[str, Any]:
        """Classify a transition so CFW can bound recovery loops."""
        before = self._normal_rank.get(from_state)
        after = self._normal_rank.get(to_state)
        path_class = str(edge.get("path_class") or ("normal" if after is not None else "unranked"))
        progress_class = str(edge["progress_class"])
        return {"edge_id": edge["id"],
                "path_class": path_class,
                "progress_class": progress_class,
                "work_class": str(edge["work_class"]),
                "domain_effect": str(edge["domain_effect"]),
                "normal_path_rank_before": before,
                "normal_path_rank_after": after}

    def _is_consequential(self, edge: Mapping[str, Any], to_state: str) -> bool:
        return edge.get("consequential") is True

    def _evidence_is_valid(self, kind: str, item: Mapping[str, Any], *, consequential: bool = False) -> bool:
        spec = self.evidence_registry.get(kind)
        if spec is None:
            return (not consequential) or (bool(item.get("content_digest"))
                                            and str(item.get("issuer") or "").startswith("host:"))
        issuer = item.get("issuer")
        schema = item.get("schema")
        validator = item.get("validator")
        if issuer not in set(spec.get("allowed_issuers") or ()) or schema != spec.get("schema") or validator != spec.get("validator"):
            return False
        if consequential and not (item.get("attestation_digest") or item.get("content_digest")):
            return False
        return True


    def transition(self, subject_ref: str, from_state: str, to_state: str, *, trigger: Optional[str] = None,
                   evidence_refs: Iterable[Mapping[str, Any] | str] = ()) -> TransitionDecision:
        if not isinstance(subject_ref, str) or not subject_ref.strip():
            return TransitionDecision(False, "subject_ref required", from_state, to_state, trigger, [])
        if from_state not in self.states or to_state not in self.states:
            return TransitionDecision(False, "unknown state", from_state, to_state, trigger, [])
        matches = self.matching_edges(from_state, to_state, trigger)
        if matches:
            exact = [edge for edge in matches if edge.get("from") == from_state]
            matches = exact or matches  # exact edges explicitly outrank wildcard edges
        if len(matches) > 1:
            return TransitionDecision(False, "ambiguous transition edges", from_state,
                                     to_state, trigger, [])
        for edge in matches:
            required = list(edge.get("required_evidence") or [])
            consequential = self._is_consequential(edge, to_state)
            evidence: List[Mapping[str, Any]] = []
            missing = []
            for item in evidence_refs:
                if isinstance(item, str):
                    if self.evidence_store is None:
                        continue
                    try:
                        evidence.extend(self.evidence_store.resolve([item]))
                    except TransitionError:
                        continue
                elif isinstance(item, Mapping):
                    # Once a trusted store is installed, caller metadata is only
                    # a lookup hint; resolve the reference and use the stored
                    # record for the actual authorization decision.
                    if self.evidence_store is not None and item.get("ref"):
                        try:
                            evidence.extend(self.evidence_store.resolve([str(item["ref"])]))
                        except TransitionError:
                            continue
                    else:
                        evidence.append(item)
            for kind in required:
                valid = [item for item in evidence if isinstance(item, Mapping) and item.get("kind") == kind and item.get("ref") and item.get("subject_ref") == subject_ref and item.get("observed_at") and item.get("invalidated") is not True and self._evidence_is_valid(kind, item, consequential=consequential)]
                if not valid:
                    missing.append(kind)
            if missing:
                return TransitionDecision(
                    False, f"missing evidence kinds: {', '.join(missing)}", from_state,
                    to_state, trigger, required, dict(edge.get("evidence_freshness") or {}))
            return TransitionDecision(True, "allowed", from_state, to_state, trigger,
                                      required, dict(edge.get("evidence_freshness") or {}),
                                      **self._progress_facts(edge, from_state, to_state))
        return TransitionDecision(False, "transition not declared", from_state, to_state, trigger, [])

    def matching_edges(self, from_state: str, to_state: str,
                       trigger: Optional[str]) -> List[Dict[str, Any]]:
        matches = []
        for edge in self.transitions:
            if edge.get("from") not in (from_state, "*") or edge.get("to") != to_state:
                continue
            edge_trigger = edge.get("trigger")
            if edge_trigger is not None and edge_trigger != trigger:
                continue
            matches.append(edge)
        if matches:
            exact = [edge for edge in matches if edge.get("from") == from_state]
            matches = exact or matches
        return matches
