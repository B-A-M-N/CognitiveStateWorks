"""Engine-neutral workflow contracts and trusted engine registry.

Bundles describe data. Engine implementations are executable host code and
enter the registry only through explicit built-in registration or a host trust
decision; a bundle cannot import arbitrary Python by naming a module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class WorkflowIdentity:
    namespace_id: str
    application_id: str
    application_instance_id: str
    workflow_id: str
    subject_ref: str
    statework_id: str
    contract_version: str


@dataclass(frozen=True)
class WorkflowStep:
    step_id: str
    label: str
    work_class: str
    domain_effect: str
    required_evidence: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowSnapshot:
    identity: WorkflowIdentity
    engine_kind: str
    revision: int
    data: Mapping[str, Any]
    current_state: str | None = None
    completed: bool = False
    eligible_steps: tuple[WorkflowStep, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))


@dataclass(frozen=True)
class WorkflowDecision:
    allowed: bool
    reason: str
    engine_kind: str
    step_id: str
    prior_revision: int
    revision: int
    work_class: str
    domain_effect: str
    progress_class: str
    current_state: str | None
    previous_state: str | None
    completed: bool
    evidence_refs: tuple[str, ...] = ()
    state_data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_data", MappingProxyType(dict(self.state_data)))

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason,
                "engine_kind": self.engine_kind, "step_id": self.step_id,
                "prior_revision": self.prior_revision, "revision": self.revision,
                "work_class": self.work_class, "domain_effect": self.domain_effect,
                "progress_class": self.progress_class,
                "current_state": self.current_state,
                "previous_state": self.previous_state,
                "completed": self.completed,
                "evidence_refs": list(self.evidence_refs),
                "state_data": dict(self.state_data)}


@dataclass(frozen=True)
class WorkflowProgressFact:
    statework_id: str
    subject_ref: str
    engine_kind: str
    step_id: str
    revision: int
    progress_class: str
    completed: bool
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"statework_id": self.statework_id, "subject_ref": self.subject_ref,
                "engine_kind": self.engine_kind, "step_id": self.step_id,
                "revision": self.revision, "progress_class": self.progress_class,
                "completed": self.completed, "evidence_refs": list(self.evidence_refs)}


class WorkflowEngine(Protocol):
    kind: str
    contract_version: str

    def validate_contract(self, contract: Mapping[str, Any]) -> None: ...
    def initialize(self, identity: WorkflowIdentity,
                   contract: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def inspect(self, identity: WorkflowIdentity, contract: Mapping[str, Any],
                state: Mapping[str, Any], revision: int) -> WorkflowSnapshot: ...
    def eligible_steps(self, identity: WorkflowIdentity,
                       contract: Mapping[str, Any],
                       snapshot: WorkflowSnapshot) -> tuple[WorkflowStep, ...]: ...
    def apply(self, identity: WorkflowIdentity, contract: Mapping[str, Any],
              snapshot: WorkflowSnapshot, *, step_id: str,
              evidence: Sequence[Mapping[str, Any]]) -> WorkflowDecision: ...


class EngineRegistry:
    """Host-owned engine registry. Runtime bundles can only select known IDs."""
    def __init__(self) -> None:
        self._engines: dict[str, WorkflowEngine] = {}
        self._trusted_hashes: dict[str, str] = {}

    def register(self, engine: WorkflowEngine, *, implementation_hash: str,
                 trusted: bool = False) -> None:
        if not trusted:
            raise PermissionError("workflow engine registration requires explicit host trust")
        if not engine.kind or len(engine.kind) > 64:
            raise ValueError("workflow engine kind must be bounded text")
        if len(implementation_hash) != 64 or any(
                char not in "0123456789abcdef" for char in implementation_hash):
            raise ValueError("workflow engine implementation hash must be SHA-256")
        prior = self._trusted_hashes.get(engine.kind)
        if prior is not None and prior != implementation_hash:
            raise ValueError(f"workflow engine {engine.kind!r} is already registered differently")
        self._engines[engine.kind] = engine
        self._trusted_hashes[engine.kind] = implementation_hash

    def get(self, kind: str) -> WorkflowEngine:
        try:
            return self._engines[kind]
        except KeyError as exc:
            raise ValueError(f"workflow engine {kind!r} is unavailable or untrusted") from exc

    @property
    def identities(self) -> Mapping[str, str]:
        return MappingProxyType(dict(self._trusted_hashes))


class StateMachineWorkflowEngine:
    """Normalize the existing transition engine behind the generic SPI."""
    kind = "state_machine"
    contract_version = "state-machine/v1"

    def __init__(self, transition_engine: Any):
        self._transition_engine = transition_engine

    def validate_contract(self, contract: Mapping[str, Any]) -> None:
        if not isinstance(contract.get("initial_state"), str):
            raise ValueError("state_machine contract requires initial_state")
        if set(contract.get("completion_states") or ()) - set(contract.get("states") or ()):
            raise ValueError("state_machine completion_states must be declared")

    def initialize(self, identity: WorkflowIdentity,
                   contract: Mapping[str, Any]) -> Mapping[str, Any]:
        self.validate_contract(contract)
        return {"state": str(contract["initial_state"])}

    def eligible_steps(self, identity: WorkflowIdentity,
                       contract: Mapping[str, Any],
                       snapshot: WorkflowSnapshot) -> tuple[WorkflowStep, ...]:
        state = snapshot.current_state
        rows = []
        for edge in contract.get("transitions") or ():
            if edge.get("from") not in {"*", state}:
                continue
            rows.append(WorkflowStep(
                step_id=str(edge["id"]), label=str(edge.get("trigger") or edge["id"]),
                work_class=str(edge.get("work_class") or "workflow"),
                domain_effect=str(edge.get("domain_effect") or "workflow_state"),
                required_evidence=tuple(edge.get("required_evidence") or ())))
        return tuple(rows)

    def resolve_legacy_step(self, contract: Mapping[str, Any], *, current_state: str,
                            to_state: str, trigger: str | None) -> str:
        matches = [edge for edge in contract.get("transitions") or ()
                   if edge.get("from") in {"*", current_state}
                   and edge.get("to") == to_state
                   and edge.get("trigger") in {None, trigger}]
        exact = [edge for edge in matches if edge.get("from") == current_state]
        matches = exact or matches
        if len(matches) != 1:
            raise ValueError("legacy state transition does not identify one workflow step")
        return str(matches[0]["id"])

    def inspect(self, identity: WorkflowIdentity, contract: Mapping[str, Any],
                state: Mapping[str, Any], revision: int) -> WorkflowSnapshot:
        current = state.get("state") or contract.get("initial_state")
        provisional = WorkflowSnapshot(
            identity, self.kind, revision, state, str(current),
            str(current) in set(contract.get("completion_states") or ()))
        return WorkflowSnapshot(
            identity, self.kind, revision, state, str(current), provisional.completed,
            self.eligible_steps(identity, contract, provisional))

    def apply(self, identity: WorkflowIdentity, contract: Mapping[str, Any],
              snapshot: WorkflowSnapshot, *, step_id: str,
              evidence: Sequence[Mapping[str, Any]]) -> WorkflowDecision:
        edge = next((item for item in contract.get("transitions") or ()
                     if item.get("id") == step_id), None)
        if edge is None:
            raise ValueError(f"unknown workflow step {step_id!r}")
        target = str(edge.get("to") or "")
        trigger = edge.get("trigger")
        decision = self._transition_engine.transition(
            identity.subject_ref, str(snapshot.current_state), target,
            trigger=trigger, evidence_refs=evidence)
        prior = snapshot.revision
        next_revision = prior + int(decision.allowed)
        next_state = target if decision.allowed else snapshot.current_state
        return WorkflowDecision(
            allowed=bool(decision.allowed), reason=str(decision.reason),
            engine_kind=self.kind, step_id=step_id, prior_revision=prior,
            revision=next_revision,
            work_class=str(decision.work_class or edge.get("work_class") or "workflow"),
            domain_effect=str(decision.domain_effect or edge.get("domain_effect") or "workflow_state"),
            progress_class=str(decision.progress_class), current_state=next_state,
            previous_state=snapshot.current_state,
            completed=next_state in set(contract.get("completion_states") or ()),
            evidence_refs=tuple(str(item.get("ref") or "") for item in evidence),
            state_data={"state": next_state})


class MilestoneWorkflowEngine:
    """Checklist engine fixture proving workflows need not invent states."""
    kind = "milestone"
    contract_version = "milestone/v1"

    def validate_contract(self, contract: Mapping[str, Any]) -> None:
        steps = contract.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError("milestone contract requires steps")
        ids = [str(step.get("id") or "") for step in steps]
        if any(not value for value in ids) or len(ids) != len(set(ids)):
            raise ValueError("milestone step IDs must be unique and non-empty")
        known = set(ids)
        for step in steps:
            dependencies = set(step.get("depends_on") or ())
            if dependencies - known or str(step.get("id")) in dependencies:
                raise ValueError("milestone dependencies must reference other steps")
        self._topological_order(steps)

    @staticmethod
    def _topological_order(steps: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
        remaining = {str(step["id"]): set(step.get("depends_on") or ()) for step in steps}
        ordered: list[str] = []
        while remaining:
            ready = sorted(key for key, deps in remaining.items() if deps.issubset(ordered))
            if not ready:
                raise ValueError("milestone dependencies contain a cycle")
            for key in ready:
                ordered.append(key)
                del remaining[key]
        return tuple(ordered)

    def initialize(self, identity: WorkflowIdentity,
                   contract: Mapping[str, Any]) -> Mapping[str, Any]:
        self.validate_contract(contract)
        return {"completed_steps": []}

    def eligible_steps(self, identity: WorkflowIdentity,
                       contract: Mapping[str, Any],
                       snapshot: WorkflowSnapshot) -> tuple[WorkflowStep, ...]:
        completed = set(snapshot.data.get("completed_steps") or ())
        return tuple(WorkflowStep(
            step_id=str(item["id"]), label=str(item.get("label") or item["id"]),
            work_class=str(item.get("work_class") or "milestone"),
            domain_effect=str(item.get("domain_effect") or "workflow_milestone"),
            required_evidence=tuple(item.get("required_evidence") or ()),
            dependencies=tuple(item.get("depends_on") or ()))
            for item in contract.get("steps") or ()
            if str(item["id"]) not in completed
            and set(item.get("depends_on") or ()).issubset(completed))

    def inspect(self, identity: WorkflowIdentity, contract: Mapping[str, Any],
                state: Mapping[str, Any], revision: int) -> WorkflowSnapshot:
        self.validate_contract(contract)
        completed = set(state.get("completed_steps") or ())
        done = completed.issuperset(str(item["id"]) for item in contract["steps"])
        provisional = WorkflowSnapshot(identity, self.kind, revision, state,
                                        completed=done)
        return WorkflowSnapshot(identity, self.kind, revision, state, completed=done,
                                eligible_steps=self.eligible_steps(identity, contract, provisional))

    def apply(self, identity: WorkflowIdentity, contract: Mapping[str, Any],
              snapshot: WorkflowSnapshot, *, step_id: str,
              evidence: Sequence[Mapping[str, Any]]) -> WorkflowDecision:
        step = next((item for item in contract.get("steps") or ()
                     if str(item.get("id")) == step_id), None)
        if step is None:
            raise ValueError(f"unknown milestone step {step_id!r}")
        eligible = {item.step_id for item in snapshot.eligible_steps}
        if step_id not in eligible:
            return WorkflowDecision(False, "milestone dependencies are incomplete", self.kind,
                                    step_id, snapshot.revision, snapshot.revision,
                                    str(step.get("work_class") or "milestone"),
                                    str(step.get("domain_effect") or "workflow_milestone"),
                                    "LATERAL", None, None, snapshot.completed,
                                    tuple(str(item.get("ref") or "") for item in evidence),
                                    dict(snapshot.data))
        required_kinds = set(step.get("required_evidence") or ())
        found_kinds = {str(item.get("kind") or "") for item in evidence}
        if not required_kinds.issubset(found_kinds):
            return WorkflowDecision(False, "milestone evidence requirements are not met", self.kind,
                                    step_id, snapshot.revision, snapshot.revision,
                                    str(step.get("work_class") or "milestone"),
                                    str(step.get("domain_effect") or "workflow_milestone"),
                                    "LATERAL", None, None, snapshot.completed,
                                    tuple(str(item.get("ref") or "") for item in evidence),
                                    dict(snapshot.data))
        completed = sorted(set(snapshot.data.get("completed_steps") or ()) | {step_id})
        done = len(completed) == len(contract["steps"])
        progress = "TERMINAL" if done else str(step.get("progress_class") or "FORWARD_PROGRESS")
        return WorkflowDecision(True, "milestone recorded", self.kind, step_id,
                                snapshot.revision, snapshot.revision + 1,
                                str(step.get("work_class") or "milestone"),
                                str(step.get("domain_effect") or "workflow_milestone"),
                                progress, None, None, done,
                                tuple(str(item.get("ref") or "") for item in evidence),
                                {"completed_steps": completed})


__all__ = ["WorkflowIdentity", "WorkflowStep", "WorkflowSnapshot",
           "WorkflowDecision", "WorkflowProgressFact", "WorkflowEngine",
           "EngineRegistry", "StateMachineWorkflowEngine", "MilestoneWorkflowEngine"]
