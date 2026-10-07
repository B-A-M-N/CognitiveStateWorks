"""Engine-neutral workflow contracts and trusted engine registry.

Bundles describe data. Engine implementations are executable host code and
enter the registry only through explicit built-in registration or a host trust
decision; a bundle cannot import arbitrary Python by naming a module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from importlib import metadata
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
    requires_facts: tuple[str, ...] = ()
    establishes_facts: tuple[str, ...] = ()
    invalidates_facts: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowSnapshot:
    identity: WorkflowIdentity
    engine_kind: str
    revision: int
    data: Mapping[str, Any]
    current_state: str | None = None
    completed: bool = False
    eligible_steps: tuple[WorkflowStep, ...] = ()
    previous_state: str | None = None
    progress_class: str | None = None

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
    requires_facts: tuple[str, ...] = ()
    establishes_facts: tuple[str, ...] = ()
    invalidates_facts: tuple[str, ...] = ()

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
                "state_data": dict(self.state_data),
                "requires_facts": list(self.requires_facts),
                "establishes_facts": list(self.establishes_facts),
                "invalidates_facts": list(self.invalidates_facts)}


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


_FACT_FIELDS = ("requires_facts", "establishes_facts", "invalidates_facts")


def validate_fact_contract(contract: Mapping[str, Any], *, step_field: str) -> None:
    """Validate engine-neutral fact declarations and their workflow effects."""
    facts = contract.get("facts", {})
    if facts is None:
        facts = {}
    if not isinstance(facts, Mapping) or len(facts) > 64:
        raise ValueError("workflow facts must be a bounded mapping")
    known: set[str] = set()
    for fact_id, declaration in facts.items():
        if (not isinstance(fact_id, str) or not fact_id or len(fact_id) > 128
                or not isinstance(declaration, Mapping)
                or set(declaration) - {"terminal_required"}
                or ("terminal_required" in declaration
                    and type(declaration["terminal_required"]) is not bool)):
            raise ValueError("workflow fact declaration is malformed")
        known.add(fact_id)

    steps = contract.get(step_field) or ()
    if not isinstance(steps, (list, tuple)) or len(steps) > 4096:
        raise ValueError("workflow steps or transitions exceed their bound")
    for step in steps:
        if not isinstance(step, Mapping):
            raise ValueError("workflow step or transition is malformed")
        effects: dict[str, set[str]] = {}
        for name in _FACT_FIELDS:
            values = step.get(name, ())
            if values is None:
                values = ()
            if (not isinstance(values, (list, tuple)) or len(values) > 64
                    or any(not isinstance(value, str) or not value or len(value) > 128
                           for value in values)
                    or len(values) != len(set(values))
                    or set(values) - known):
                raise ValueError(f"workflow {name} references invalid fact IDs")
            effects[name] = set(values)
        if effects["establishes_facts"] & effects["invalidates_facts"]:
            raise ValueError("a workflow step cannot establish and invalidate the same fact")


def terminal_required_facts(contract: Mapping[str, Any]) -> frozenset[str]:
    facts = contract.get("facts", {})
    if facts is None:
        facts = {}
    if not isinstance(facts, Mapping):
        return frozenset()
    return frozenset(str(fact_id) for fact_id, declaration in facts.items()
                     if isinstance(declaration, Mapping)
                     and declaration.get("terminal_required") is True)


def active_fact_ids(data: Mapping[str, Any]) -> frozenset[str]:
    """Read the normalized fact projection carried by an inspection snapshot."""
    ledger = data.get("fact_ledger") or ()
    if isinstance(ledger, Mapping):
        ledger = tuple(ledger.values())
    if not isinstance(ledger, (list, tuple)):
        return frozenset()
    return frozenset(str(item.get("fact_id")) for item in ledger
                     if isinstance(item, Mapping) and item.get("status") == "ESTABLISHED")


class EngineRegistry:
    """Host-owned engine registry. Runtime bundles can only select known IDs."""
    ENTRY_POINT_GROUP = "cognitive_statework.engines"

    def __init__(self) -> None:
        self._engines: dict[str, WorkflowEngine] = {}
        self._trusted_hashes: dict[str, str] = {}

    def register(self, engine: WorkflowEngine, *, implementation_hash: str,
                 trusted: bool = False) -> None:
        if not trusted:
            raise PermissionError("workflow engine registration requires explicit host trust")
        kind = getattr(engine, "kind", None)
        contract_version = getattr(engine, "contract_version", None)
        if not isinstance(kind, str) or not kind.strip() or len(kind) > 64:
            raise ValueError("workflow engine kind must be bounded text")
        if (not isinstance(contract_version, str) or not contract_version.strip()
                or len(contract_version) > 128):
            raise TypeError("workflow engine must declare a contract version")
        if any(not callable(getattr(engine, method, None)) for method in (
                "validate_contract", "initialize", "inspect", "eligible_steps", "apply")):
            raise TypeError("workflow engine does not implement the complete engine interface")
        if len(implementation_hash) != 64 or any(
                char not in "0123456789abcdef" for char in implementation_hash):
            raise ValueError("workflow engine implementation hash must be SHA-256")
        prior = self._trusted_hashes.get(engine.kind)
        if prior is not None and prior != implementation_hash:
            raise ValueError(f"workflow engine {engine.kind!r} is already registered differently")
        self._engines[engine.kind] = engine
        self._trusted_hashes[engine.kind] = implementation_hash

    @staticmethod
    def entry_point_identity(entry_point: Any) -> str:
        distribution = getattr(entry_point, "dist", None)
        if distribution is None:
            raise ValueError("workflow engine entry point has no owning distribution")
        name = str((getattr(distribution, "metadata", {}) or {}).get("Name") or "")
        version = str(getattr(distribution, "version", "") or "")
        if not name or not version:
            raise ValueError("workflow engine entry point distribution identity is incomplete")
        return f"{name}=={version}:{entry_point.name}={entry_point.value}"

    @staticmethod
    def entry_point_source_hash(entry_point: Any) -> str:
        distribution = entry_point.dist
        module_name = str(entry_point.value).split(":", 1)[0]
        if not module_name or any(not part.isidentifier() for part in module_name.split(".")):
            raise ValueError("workflow engine entry point must name a Python module")
        module_path = module_name.replace(".", "/")
        candidates = {module_path + ".py", module_path + "/__init__.py"}
        files = getattr(distribution, "files", None) or ()
        normalized = {str(item).replace("\\", "/"): item for item in files}
        module_matches = [normalized[name] for name in candidates if name in normalized]
        if len(module_matches) != 1:
            raise ValueError("workflow engine entry point module must be one packaged source file")
        source_files = sorted((item for item in files
                               if str(item).replace("\\", "/").endswith(".py")),
                              key=lambda item: str(item))
        if not source_files or len(source_files) > 4096:
            raise ValueError("workflow engine distribution has an invalid Python source inventory")
        digest = sha256()
        total_bytes = 0
        for item in source_files:
            source = distribution.locate_file(item)
            if source.is_symlink() or not source.is_file():
                raise ValueError("workflow engine distribution contains missing or linked source")
            contents = source.read_bytes()
            total_bytes += len(contents)
            if total_bytes > 64 * 1024 * 1024:
                raise ValueError("workflow engine distribution source exceeds the hash bound")
            digest.update(str(item).replace("\\", "/").encode("utf-8"))
            digest.update(b"\0")
            digest.update(contents)
            digest.update(b"\0")
        return digest.hexdigest()

    def _load_entries(self, trusted_entry_points: Mapping[str, str],
                      entry_points: Iterable[Any]) -> tuple[str, ...]:
        """Load only source-hash-pinned entries explicitly adopted by the host."""
        if not isinstance(trusted_entry_points, Mapping):
            raise TypeError("trusted engine entry points must be a host-owned mapping")
        if not trusted_entry_points:
            return ()
        discovered: dict[str, Any] = {}
        for entry_point in entry_points:
            try:
                identity = self.entry_point_identity(entry_point)
            except (AttributeError, TypeError, ValueError):
                continue
            if identity not in trusted_entry_points:
                continue
            if identity in discovered:
                raise ValueError(f"duplicate workflow engine entry point {identity!r}")
            discovered[identity] = entry_point
        missing = set(trusted_entry_points) - set(discovered)
        if missing:
            raise ValueError(f"trusted workflow engine entry points are unavailable: {sorted(missing)}")

        loaded: list[str] = []
        for identity, expected_hash in trusted_entry_points.items():
            if (not isinstance(expected_hash, str) or len(expected_hash) != 64
                    or any(char not in "0123456789abcdef" for char in expected_hash)):
                raise ValueError("trusted workflow engine pins must be lowercase SHA-256 hashes")
            entry_point = discovered[identity]
            actual_hash = self.entry_point_source_hash(entry_point)
            if actual_hash != expected_hash:
                raise PermissionError(
                    f"workflow engine entry point source differs from host trust pin: {identity}")
            implementation = entry_point.load()
            engine = implementation() if isinstance(implementation, type) else implementation
            if str(getattr(engine, "kind", "")) != str(entry_point.name):
                raise ValueError("workflow engine kind must match its entry point name")
            self.register(engine, implementation_hash=actual_hash, trusted=True)
            loaded.append(engine.kind)
        return tuple(loaded)

    def load_trusted_entry_points(self, trusted_entry_points: Mapping[str, str]
                                  ) -> tuple[str, ...]:
        """Load explicitly adopted Python engines; data bundles never trigger imports."""
        if not trusted_entry_points:
            return ()
        entries = metadata.entry_points(group=self.ENTRY_POINT_GROUP)
        return self._load_entries(trusted_entry_points, entries)

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
        validate_fact_contract(contract, step_field="transitions")

    def initialize(self, identity: WorkflowIdentity,
                   contract: Mapping[str, Any]) -> Mapping[str, Any]:
        self.validate_contract(contract)
        return {"state": str(contract["initial_state"])}

    def eligible_steps(self, identity: WorkflowIdentity,
                       contract: Mapping[str, Any],
                       snapshot: WorkflowSnapshot) -> tuple[WorkflowStep, ...]:
        state = snapshot.current_state
        established = active_fact_ids(snapshot.data)
        rows = []
        for edge in contract.get("transitions") or ():
            if edge.get("from") not in {"*", state}:
                continue
            requires_facts = tuple(edge.get("requires_facts") or ())
            if not set(requires_facts).issubset(established):
                continue
            terminal_required = terminal_required_facts(contract)
            next_facts = ((established - set(edge.get("invalidates_facts") or ()))
                          | set(edge.get("establishes_facts") or ()))
            if (edge.get("to") in set(contract.get("completion_states") or ())
                    and not terminal_required.issubset(next_facts)):
                continue
            rows.append(WorkflowStep(
                step_id=str(edge["id"]), label=str(edge.get("trigger") or edge["id"]),
                work_class=str(edge.get("work_class") or "workflow"),
                domain_effect=str(edge.get("domain_effect") or "workflow_state"),
                required_evidence=tuple(edge.get("required_evidence") or ()),
                requires_facts=requires_facts,
                establishes_facts=tuple(edge.get("establishes_facts") or ()),
                invalidates_facts=tuple(edge.get("invalidates_facts") or ())))
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
        terminal_facts = terminal_required_facts(contract)
        established_facts = active_fact_ids(state)
        provisional = WorkflowSnapshot(
            identity, self.kind, revision, state, str(current),
            (str(current) in set(contract.get("completion_states") or ())
             and terminal_facts.issubset(established_facts)))
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
        requires_facts = tuple(edge.get("requires_facts") or ())
        established = active_fact_ids(snapshot.data)
        establishes_facts = tuple(edge.get("establishes_facts") or ())
        invalidates_facts = tuple(edge.get("invalidates_facts") or ())
        next_facts = (established - set(invalidates_facts)) | set(establishes_facts)
        missing_facts = set(requires_facts) - established
        terminal_required = terminal_required_facts(contract)
        terminal_facts_missing = (
            target in set(contract.get("completion_states") or ())
            and not terminal_required.issubset(next_facts))
        if missing_facts or terminal_facts_missing:
            return WorkflowDecision(
                False, ("required workflow facts are not established" if missing_facts
                        else "terminal-required workflow facts are not established"), self.kind,
                step_id, snapshot.revision, snapshot.revision,
                str(edge.get("work_class") or "workflow"),
                str(edge.get("domain_effect") or "workflow_state"),
                "LATERAL", snapshot.current_state, snapshot.current_state,
                snapshot.completed, tuple(str(item.get("ref") or "") for item in evidence),
                {"state": snapshot.current_state}, requires_facts=requires_facts,
                establishes_facts=establishes_facts,
                invalidates_facts=invalidates_facts)
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
            completed=(next_state in set(contract.get("completion_states") or ())
                       and terminal_required_facts(contract).issubset(next_facts)),
            evidence_refs=tuple(str(item.get("ref") or "") for item in evidence),
            state_data={"state": next_state},
            requires_facts=requires_facts,
            establishes_facts=establishes_facts,
            invalidates_facts=invalidates_facts)


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
        validate_fact_contract(contract, step_field="steps")
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
        return {"milestone_receipts": []}

    def eligible_steps(self, identity: WorkflowIdentity,
                       contract: Mapping[str, Any],
                       snapshot: WorkflowSnapshot) -> tuple[WorkflowStep, ...]:
        completed = set(snapshot.data.get("completed_steps") or ())
        established = active_fact_ids(snapshot.data)
        return tuple(WorkflowStep(
            step_id=str(item["id"]), label=str(item.get("label") or item["id"]),
            work_class=str(item.get("work_class") or "milestone"),
            domain_effect=str(item.get("domain_effect") or "workflow_milestone"),
            required_evidence=tuple(item.get("required_evidence") or ()),
            dependencies=tuple(item.get("depends_on") or ()),
            requires_facts=tuple(item.get("requires_facts") or ()),
            establishes_facts=tuple(item.get("establishes_facts") or ()),
            invalidates_facts=tuple(item.get("invalidates_facts") or ()))
            for item in contract.get("steps") or ()
            if str(item["id"]) not in completed
            and set(item.get("depends_on") or ()).issubset(completed)
            and set(item.get("requires_facts") or ()).issubset(established))

    def inspect(self, identity: WorkflowIdentity, contract: Mapping[str, Any],
                state: Mapping[str, Any], revision: int) -> WorkflowSnapshot:
        self.validate_contract(contract)
        completed = set(state.get("completed_steps") or ())
        done = (completed.issuperset(str(item["id"]) for item in contract["steps"])
                and terminal_required_facts(contract).issubset(active_fact_ids(state)))
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
            reason = ("milestone dependencies or required facts are incomplete"
                      if step_id in {str(item["id"]) for item in contract["steps"]}
                      else "unknown milestone step")
            return WorkflowDecision(False, reason, self.kind,
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
        requires_facts = tuple(step.get("requires_facts") or ())
        establishes_facts = tuple(step.get("establishes_facts") or ())
        invalidates_facts = tuple(step.get("invalidates_facts") or ())
        established = active_fact_ids(snapshot.data)
        next_facts = (established - set(invalidates_facts)) | set(establishes_facts)
        all_steps_done = len(completed) == len(contract["steps"])
        done = (all_steps_done
                and terminal_required_facts(contract).issubset(next_facts))
        progress = ("TERMINAL" if all_steps_done
                    else str(step.get("progress_class") or "FORWARD_PROGRESS"))
        receipt = {
            "step_id": step_id,
            "evidence_refs": [str(item.get("ref") or "") for item in evidence],
            "workflow_revision": snapshot.revision + 1,
            "requires_facts": list(requires_facts),
            "establishes_facts": list(establishes_facts),
            "invalidates_facts": list(invalidates_facts),
        }
        receipts = list(snapshot.data.get("milestone_receipts") or ())
        if len(receipts) >= 4096:
            raise ValueError("milestone receipt ledger exceeds its bound")
        receipts.append(receipt)
        return WorkflowDecision(True, "milestone recorded", self.kind, step_id,
                                snapshot.revision, snapshot.revision + 1,
                                str(step.get("work_class") or "milestone"),
                                str(step.get("domain_effect") or "workflow_milestone"),
                                progress, None, None, done,
                                tuple(str(item.get("ref") or "") for item in evidence),
                                {"milestone_receipts": receipts},
                                requires_facts=requires_facts,
                                establishes_facts=establishes_facts,
                                invalidates_facts=invalidates_facts)


__all__ = ["WorkflowIdentity", "WorkflowStep", "WorkflowSnapshot",
           "WorkflowDecision", "WorkflowProgressFact", "WorkflowEngine",
           "EngineRegistry", "StateMachineWorkflowEngine", "MilestoneWorkflowEngine"]
