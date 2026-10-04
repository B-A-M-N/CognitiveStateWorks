"""Workflow selection and authority over legal StateWork activation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

if __package__:
    from .errors import TransitionError
    from .evidence import EvidenceStore
    from .resources import ROOT, _load_yaml
    from .selection_store import WorkflowSelectionStore
    from .state_store import SubjectStateStore
    from .transition_engine import TransitionEngine
    from .workflow_controller import StandaloneStateWorkController
    from .workflow_engines import (EngineRegistry, MilestoneWorkflowEngine,
                                   StateMachineWorkflowEngine, WorkflowDecision,
                                   WorkflowIdentity, WorkflowProgressFact,
                                   WorkflowSnapshot)
    from .composition_rules import depends_on, validate_selection
else:
    from errors import TransitionError
    from evidence import EvidenceStore
    from resources import ROOT, _load_yaml
    from selection_store import WorkflowSelectionStore
    from state_store import SubjectStateStore
    from transition_engine import TransitionEngine
    from workflow_controller import StandaloneStateWorkController
    from workflow_engines import (EngineRegistry, MilestoneWorkflowEngine,
                                  StateMachineWorkflowEngine, WorkflowDecision,
                                  WorkflowIdentity, WorkflowProgressFact,
                                  WorkflowSnapshot)
    from composition_rules import depends_on, validate_selection


WORKFLOW_PORT_VERSION = "1.2.0"


def load_compiled_registry(root: Optional[Path] = None, *,
                           verify_bundles: bool = True) -> dict[str, Any]:
    """Load the registry lazily to avoid the control-plane import cycle."""
    if __package__:
        from .registry import load_compiled_registry as implementation
    else:
        from registry import load_compiled_registry as implementation
    return implementation(root, verify_bundles=verify_bundles)

class WorkflowAuthority:
    """Generic host authority over compiled StateWork workflow engines.

    Engine choice and step semantics stay inside CSW. Consumers inspect a
    normalized snapshot and submit an engine-neutral step identifier.
    """
    workflow_port_version = WORKFLOW_PORT_VERSION

    def __init__(self, *, root: Optional[Path] = None,
                 state_store: Optional[SubjectStateStore] = None,
                 evidence_store: Optional[EvidenceStore] = None,
                 engine_registry: Optional[EngineRegistry] = None,
                 selection_store: Optional[WorkflowSelectionStore] = None):
        self.root = Path(root or ROOT)
        self.state_store = state_store or SubjectStateStore(
            self.root / "state" / "subjects.json")
        self.evidence_store = evidence_store or EvidenceStore()
        self.engine_registry = engine_registry or EngineRegistry()
        self.selection_store = selection_store or WorkflowSelectionStore(
            self.root / "state" / "workflow-selections.json")
        self._controllers: Dict[str, StandaloneStateWorkController] = {}
        # The registry is a process-lifetime trust pin. Authority calls never
        # re-read it implicitly, so one request cannot mix registry versions.
        self._compiled_registry = load_compiled_registry(self.root)
        self._registry_hash = str(self._compiled_registry["registry_hash"])

    @property
    def registry_hash(self) -> str:
        return self._registry_hash

    def reload_registry(self, *, expected_registry_hash: str) -> str:
        """Explicitly replace the process pin after the caller names its hash."""
        compiled = load_compiled_registry(self.root)
        actual = str(compiled.get("registry_hash") or "")
        if actual != expected_registry_hash:
            raise TransitionError("compiled registry hash does not match the requested pin")
        self._compiled_registry = compiled
        self._registry_hash = actual
        self._controllers.clear()
        return actual

    def _bundle(self, statework_id: str, contract_hash: Optional[str] = None
                ) -> tuple[dict[str, Any], dict[str, Any], str, Any, dict[str, Any]]:
        compiled = self._compiled_registry
        entry = next((item for item in compiled.get("stateworks") or ()
                      if item.get("id") == statework_id), None)
        if entry is None:
            raise TransitionError(f"StateWork {statework_id!r} is unavailable")
        manifest = dict(entry.get("manifest") or {})
        engine_decl = manifest.get("engine") or {
            "kind": "state_machine", "contract": "transitions.yaml",
            "contract_version": StateMachineWorkflowEngine.contract_version}
        if not isinstance(engine_decl, Mapping):
            raise TransitionError("StateWork engine declaration must be a mapping")
        kind = str(engine_decl.get("kind") or "")
        engine_pin = dict(entry.get("engine") or {})
        contract_name = str(engine_pin.get("contract_path") or engine_decl.get("contract") or "")
        if (not contract_name or Path(contract_name).is_absolute()
                or ".." in Path(contract_name).parts):
            raise TransitionError("workflow contract path escapes its bundle")
        bundle_root = Path(str(entry.get("bundle_root") or "")).resolve()
        if not bundle_root.is_dir():
            raise TransitionError(f"StateWork {statework_id!r} bundle root is unavailable")
        contract_path = (bundle_root / contract_name).resolve()
        try:
            contract_path.relative_to(bundle_root)
        except ValueError as exc:
            raise TransitionError("workflow contract path escapes its bundle") from exc
        if not contract_path.is_file():
            raise TransitionError("workflow contract is missing")
        contract = _load_yaml(contract_path) or {}
        digest = hashlib.sha256(json.dumps(
            contract, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        if contract_hash and contract_hash != digest:
            raise TransitionError("workflow contract differs from the CFW policy pin")
        if engine_pin.get("contract_hash") and engine_pin["contract_hash"] != digest:
            raise TransitionError("workflow contract differs from the compiled registry pin")
        evidence_registry = dict(compiled.get("evidence_registry") or {"kinds": {}})
        if kind == "state_machine":
            transition_engine = TransitionEngine(
                dict(contract), evidence_registry=evidence_registry,
                require_registered=True, evidence_store=self.evidence_store)
            engine = StateMachineWorkflowEngine(transition_engine)
        elif kind == "milestone":
            engine = MilestoneWorkflowEngine()
        else:
            engine = self.engine_registry.get(kind)
            expected_engine_hash = dict(compiled.get("workflow_engine_hashes") or {}).get(kind)
            registered_engine_hash = self.engine_registry.identities.get(kind)
            if (expected_engine_hash is None
                    or registered_engine_hash != expected_engine_hash):
                raise TransitionError(
                    f"workflow engine {kind!r} differs from the compiled host trust pin")
        engine.validate_contract(contract)
        return manifest, dict(contract), digest, engine, evidence_registry

    @staticmethod
    def _identity(value: WorkflowIdentity | Mapping[str, Any]) -> WorkflowIdentity:
        if isinstance(value, WorkflowIdentity):
            return value
        return WorkflowIdentity(**{key: str(value[key]) for key in (
            "namespace_id", "application_id", "application_instance_id",
            "workflow_id", "subject_ref", "statework_id", "contract_version")})

    def workflow_contract_identity(self, statework_id: str,
                                   contract_hash: Optional[str] = None) -> dict[str, Any]:
        manifest, contract, digest, engine, _evidence_registry = self._bundle(
            statework_id, contract_hash)
        return {"statework_id": statework_id, "engine_kind": engine.kind,
                "contract_version": engine.contract_version,
                "contract_hash": digest, "contract": contract,
                "manifest": manifest}

    @staticmethod
    def _selection_scope(identity: WorkflowIdentity | Mapping[str, Any]
                         ) -> dict[str, str]:
        identity = WorkflowAuthority._identity(identity)
        return {name: str(getattr(identity, name))
                for name in WorkflowSelectionStore.SCOPE_FIELDS}

    @classmethod
    def _selection_compatible(cls, entries: Mapping[str, Mapping[str, Any]],
                              statework_id: str, active_ids: set[str]) -> bool:
        selected = set(active_ids) | {statework_id}
        manifests = {key: dict(entries[key].get("manifest") or {})
                     for key in selected if key in entries}
        try:
            validate_selection(manifests, selected)
        except ValueError:
            return False
        return True

    def activate_workflow(self, identity: WorkflowIdentity | Mapping[str, Any], *,
                          contract_hash: str,
                          expected_selection_revision: int,
                          activation_owner: str = "host",
                          control_session_id: Optional[str] = None,
                          intervention_id: Optional[str] = None,
                          expires_at_action: Optional[int] = None) -> dict[str, Any]:
        """Activate a StateWork only after CSW checks registration and composition."""
        lease = {
            "activation_owner": activation_owner,
            "control_session_id": control_session_id,
            "intervention_id": intervention_id,
            "expires_at_action": expires_at_action,
        }
        WorkflowSelectionStore._validate_activation_row(
            {**lease, "identity": {}, "contract_hash": contract_hash,
             "activation_revision": expected_selection_revision + 1},
            max_revision=expected_selection_revision + 1)
        identity = self._identity(identity)
        statework_id = identity.statework_id
        manifest, _contract, digest, engine, _evidence = self._bundle(
            statework_id, contract_hash)
        if digest != contract_hash:
            raise TransitionError("workflow contract pin is not current")
        scope = self._selection_scope(identity)
        selection = self.selection_store.get(scope)
        if int(selection["revision"]) != int(expected_selection_revision):
            raise TransitionError(
                f"workflow selection revision conflict: expected {expected_selection_revision}, "
                f"found {selection['revision']}; re-inspect required")
        active = dict(selection["active_workflows"])
        if statework_id in active:
            row = active[statework_id]
            if (row.get("identity") != dict(identity.__dict__)
                    or row.get("contract_hash") != digest
                    or any(row.get(key) != value for key, value in lease.items())):
                raise TransitionError(
                    "active workflow identity or lease differs from the current request")
            return selection
        if len(active) >= 16:
            raise TransitionError("active workflow set exceeds its bounds")
        compiled = self._compiled_registry
        entries = {str(item.get("id")): item for item in compiled.get("stateworks") or ()}
        if not self._selection_compatible(entries, statework_id, set(active)):
            raise TransitionError("StateWork is not composition-compatible with the active set")
        # Initialize through the same authoritative engine before publishing
        # the active selection. An interrupted activation can leave an
        # initialized but inactive subject, never an active uninitialized one.
        self.inspect_workflow(identity, contract_hash=digest)
        active[statework_id] = {
            "identity": dict(identity.__dict__), "contract_hash": digest,
            **lease, "activation_revision": expected_selection_revision + 1,
        }
        return self.selection_store.replace(
            scope, expected_revision=expected_selection_revision,
            active_workflows=active)

    def deactivate_workflow(self, *, workflow_scope: Mapping[str, Any],
                            statework_id: str,
                            expected_selection_revision: int,
                            expected_activation_owner: Optional[str] = None,
                            expected_control_session_id: Optional[str] = None,
                            expected_intervention_id: Optional[str] = None) -> dict[str, Any]:
        """Release an activation and report dependency retention explicitly.

        DP leases additionally require their session and intervention identity.
        Persistent host activations remain releasable by an explicit host-owned
        request; omitting the owner is never treated as permission.
        """
        if expected_activation_owner is None:
            raise TransitionError("workflow release requires an activation owner")
        if expected_activation_owner not in {"host", "digitalpsychology"}:
            raise TransitionError("workflow release owner is invalid")
        if (expected_activation_owner == "digitalpsychology"
                and (not expected_control_session_id or not expected_intervention_id)):
            raise TransitionError(
                "DigitalPsychology release requires its control session and intervention ID")
        if (expected_activation_owner == "host"
                and (expected_control_session_id is not None
                     or expected_intervention_id is not None)):
            raise TransitionError("host workflow release cannot carry a DP lease identity")
        selection = self.selection_store.get(workflow_scope)
        if int(selection["revision"]) != int(expected_selection_revision):
            raise TransitionError(
                f"workflow selection revision conflict: expected {expected_selection_revision}, "
                f"found {selection['revision']}; re-inspect required")
        active = dict(selection["active_workflows"])
        if statework_id not in active:
            return {**selection, "disposition": "already_inactive",
                    "statework_id": statework_id, "required_by": [],
                    "released_stateworks": []}
        row = dict(active[statework_id])
        compiled = self._compiled_registry
        entries = {str(item.get("id")): item for item in compiled.get("stateworks") or ()}
        manifests = {key: item.get("manifest") or item
                     for key, item in entries.items()}
        required_by = sorted(other_id for other_id in set(active) - {statework_id}
                             if depends_on(manifests, other_id, statework_id))
        if row.get("activation_owner") == "dependency":
            if required_by:
                return {**selection, "disposition": "retained_required",
                        "statework_id": statework_id, "required_by": required_by,
                        "released_stateworks": []}
            active.pop(statework_id)
            released = {statework_id}
            changed = True
            while changed:
                changed = False
                for retained_id, retained_row in tuple(active.items()):
                    if retained_row.get("activation_owner") != "dependency":
                        continue
                    dependents = [other_id for other_id in active
                                  if other_id != retained_id
                                  and depends_on(manifests, other_id, retained_id)]
                    if not dependents:
                        active.pop(retained_id)
                        released.add(retained_id)
                        changed = True
            updated = self.selection_store.replace(
                workflow_scope, expected_revision=expected_selection_revision,
                active_workflows=active)
            return {**updated, "disposition": "released",
                    "statework_id": statework_id, "required_by": [],
                    "released_stateworks": sorted(released)}
        for name, expected in (
                ("activation_owner", expected_activation_owner),
                ("control_session_id", expected_control_session_id),
                ("intervention_id", expected_intervention_id)):
            if expected is not None and row.get(name) != expected:
                return {**selection, "disposition": "owner_mismatch",
                        "statework_id": statework_id, "required_by": [],
                        "released_stateworks": []}
        if required_by:
            # Retain legal composition after the causal DP lease ends. The
            # dependency has its own owner and no longer advertises a live DP
            # intervention or expiry.
            active[statework_id] = {
                **row, "activation_owner": "dependency",
                "control_session_id": None, "intervention_id": None,
                "expires_at_action": None,
            }
            updated = self.selection_store.replace(
                workflow_scope, expected_revision=expected_selection_revision,
                active_workflows=active)
            return {**updated, "disposition": "retained_required",
                    "statework_id": statework_id, "required_by": required_by,
                    "released_stateworks": []}

        released = {statework_id}
        active.pop(statework_id)
        # Dependency-owned ancestors release when their final dependent goes.
        changed = True
        while changed:
            changed = False
            for retained_id, retained_row in tuple(active.items()):
                if retained_row.get("activation_owner") != "dependency":
                    continue
                dependents = [other_id for other_id in active
                              if other_id != retained_id
                              and depends_on(manifests, other_id, retained_id)]
                if not dependents:
                    active.pop(retained_id)
                    released.add(retained_id)
                    changed = True
        updated = self.selection_store.replace(
            workflow_scope, expected_revision=expected_selection_revision,
            active_workflows=active)
        return {**updated, "disposition": "released",
                "statework_id": statework_id, "required_by": [],
                "released_stateworks": sorted(released)}

    def workflow_activation_metadata(self, *, workflow_scope: Mapping[str, Any],
                                     statework_id: str) -> Optional[dict[str, Any]]:
        """Return CSW-recorded activation ownership for host reconciliation."""
        selection = self.selection_store.get(workflow_scope)
        row = selection["active_workflows"].get(statework_id)
        if row is None:
            return None
        WorkflowSelectionStore._validate_activation_row(
            row, max_revision=int(selection["revision"]))
        metadata = {name: row[name] for name in (
            "activation_owner", "control_session_id", "intervention_id",
            "activation_revision", "expires_at_action")}
        if row["activation_owner"] == "dependency":
            compiled = self._compiled_registry
            manifests = {str(item.get("id")): item.get("manifest") or item
                         for item in compiled.get("stateworks") or ()}
            metadata["required_by"] = sorted(
                other_id for other_id in selection["active_workflows"]
                if other_id != statework_id
                and depends_on(manifests, other_id, statework_id))
        return metadata

    def behavioral_snapshot(
            self, *, workflow_scope: Mapping[str, Any],
            candidate_statework_ids: Optional[Iterable[str]] = None,
            ) -> dict[str, Any]:
        """Return bounded state and legal choices from CSW-owned workflow selection.

        DigitalPsychology may rank the eligible candidates. Only CSW activates
        or deactivates them and applies their legal, evidence-bound transitions.
        """
        selection = self.selection_store.get(workflow_scope)
        candidates = (list(candidate_statework_ids) if candidate_statework_ids is not None
                      else None)
        if candidates is not None and len(candidates) > 32:
            raise TransitionError("behavioral snapshot request exceeds its bounds")

        compiled = self._compiled_registry
        entries = {str(item.get("id")): item
                   for item in compiled.get("stateworks") or ()}
        active_rows = selection["active_workflows"]
        if len(active_rows) > 16:
            raise TransitionError("active workflow set exceeds its bounds")
        active_ids: set[str] = set()
        active: list[dict[str, Any]] = []
        scope_key = WorkflowSelectionStore._scope_key(workflow_scope)
        expected_scope = json.loads(scope_key)
        for statework_id, row in sorted(active_rows.items()):
            expected_fields = {"identity", "contract_hash", "activation_owner",
                               "control_session_id", "intervention_id",
                               "activation_revision", "expires_at_action"}
            if not isinstance(row, Mapping) or set(row) != expected_fields:
                raise TransitionError("stored active workflow row is malformed")
            WorkflowSelectionStore._validate_activation_row(
                row, max_revision=int(selection["revision"]))
            raw_identity = row.get("identity")
            contract_hash = row.get("contract_hash")
            if not isinstance(raw_identity, Mapping):
                raise TransitionError("stored active workflow identity is malformed")
            identity_fields = {
                "namespace_id", "application_id", "application_instance_id",
                "workflow_id", "subject_ref", "statework_id", "contract_version",
            }
            if set(raw_identity) != identity_fields:
                raise TransitionError("stored active workflow identity is malformed")
            identity = self._identity(raw_identity)
            actual_scope = self._selection_scope(identity)
            if actual_scope != expected_scope or identity.statework_id != statework_id:
                raise TransitionError("stored active workflow escapes its selection scope")
            if statework_id not in entries:
                raise TransitionError(f"active StateWork {statework_id!r} is unavailable")
            snapshot = self.inspect_workflow(identity, contract_hash=str(contract_hash))
            active_ids.add(statework_id)
            active.append({
                "identity": dict(identity.__dict__),
                "contract_hash": str(contract_hash),
                "activation_owner": row["activation_owner"],
                "dependency_required_by": self._dependency_required_by(
                    statework_id, active_rows, entries),
                "engine_kind": snapshot.engine_kind,
                "revision": snapshot.revision,
                "current_state": snapshot.current_state,
                "completed": snapshot.completed,
                "eligible_steps": [
                    {"step_id": step.step_id, "label": step.label,
                     "work_class": step.work_class, "domain_effect": step.domain_effect,
                     "required_evidence": list(step.required_evidence),
                     "dependencies": list(step.dependencies)}
                    for step in snapshot.eligible_steps
                ],
            })

        candidates = list(entries) if candidates is None else candidates
        if any(not isinstance(item, str) or not item or len(item) > 128
               for item in candidates):
            raise TransitionError("candidate StateWork IDs must be bounded text")
        if len(candidates) != len(set(candidates)):
            raise TransitionError("candidate StateWork IDs must be unique")
        unknown = sorted(set(candidates) - set(entries))
        if unknown:
            raise TransitionError(f"unavailable candidate StateWorks: {unknown}")
        eligible = []
        for statework_id in sorted(candidates):
            if statework_id in active_ids or not self._selection_compatible(
                    entries, statework_id, active_ids):
                continue
            manifest = dict(entries[statework_id].get("manifest") or {})
            eligible.append({
                "statework_id": statework_id,
                "domain": str(manifest.get("domain") or ""),
                "purpose": str(manifest.get("purpose") or ""),
                "behavior_tags": list(manifest.get("behavior_tags") or ()),
            })

        body = {"registry_hash": compiled["registry_hash"],
                "selection_revision": int(selection["revision"]),
                "active_workflows": active,
                "eligible_stateworks": eligible}
        snapshot_id = hashlib.sha256(json.dumps(
            body, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")).hexdigest()
        return {"snapshot_id": snapshot_id, **body}

    def expire_workflow_leases(self, *, workflow_scope: Mapping[str, Any],
                               host_action_index: int) -> dict[str, Any]:
        """Explicitly expire temporary DP workflow activations at a host boundary."""
        if type(host_action_index) is not int or host_action_index < 0:
            raise TransitionError("host action index must be non-negative")
        selection = self.selection_store.get(workflow_scope)
        compiled = self._compiled_registry
        entries = {str(item.get("id")): item
                   for item in compiled.get("stateworks") or ()}
        return self._expire_workflow_leases(
            workflow_scope, selection, entries, host_action_index)

    @staticmethod
    def _dependency_required_by(
            statework_id: str, active: Mapping[str, Mapping[str, Any]],
            entries: Mapping[str, Mapping[str, Any]]) -> list[str]:
        manifests = {key: item.get("manifest") or item for key, item in entries.items()}
        return sorted(other_id for other_id in active if other_id != statework_id
                      and depends_on(manifests, other_id, statework_id))

    def _expire_workflow_leases(self, workflow_scope: Mapping[str, Any],
                                selection: Mapping[str, Any],
                                entries: Mapping[str, Mapping[str, Any]],
                                host_action_index: int) -> dict[str, Any]:
        """Release expired DP leases while retaining independently owned workflows.

        Lease boundary convention, shared with CFW and DP:

            A lease with ``expires_at_action = N`` is effective for every action
            ``<= N`` and has been released once the action index reaches
            ``N + 1``.

        The boundary is inclusive of N so that CFW's component overlay and CSW's
        workflow selection release on the same action. Treating N as already
        expired released CSW one action before CFW, which left a framework lease
        holding a control whose StateWork was gone.
        """
        active = dict(selection["active_workflows"])
        manifests = {key: item.get("manifest") or item
                     for key, item in entries.items()}
        expired = {
            statework_id for statework_id, row in active.items()
            if row.get("activation_owner") == "digitalpsychology"
            and row.get("expires_at_action") is not None
            and int(row["expires_at_action"]) < host_action_index
        }
        removed = False
        # Expired DP-owned prerequisites transition to dependency ownership;
        # they no longer claim a live intervention or lease.
        for statework_id in tuple(expired):
            if self._dependency_required_by(statework_id, active, entries):
                row = dict(active[statework_id])
                active[statework_id] = {
                    **row, "activation_owner": "dependency",
                    "control_session_id": None, "intervention_id": None,
                    "expires_at_action": None,
                }
                expired.remove(statework_id)
                removed = True

        # Remove expired leaves first, then dependency-owned ancestors whose
        # final dependent has gone.
        while True:
            candidates = set(expired) | {
                statework_id for statework_id, row in active.items()
                if row.get("activation_owner") == "dependency"}
            releasable = [statework_id for statework_id in candidates
                          if not self._dependency_required_by(
                              statework_id, active, entries)]
            if not releasable:
                break
            for statework_id in releasable:
                active.pop(statework_id, None)
                expired.discard(statework_id)
                removed = True
        if not removed:
            return dict(selection)
        return self.selection_store.replace(
            workflow_scope, expected_revision=int(selection["revision"]),
            active_workflows=active)

    def _identity_key(self, identity: WorkflowIdentity) -> str:
        return self.state_store.key(identity.__dict__)

    def _engine_snapshot(self, identity: WorkflowIdentity, contract_hash: str
                         ) -> tuple[Any, dict[str, Any], WorkflowSnapshot]:
        manifest, contract, _digest, engine, evidence_registry = self._bundle(
            identity.statework_id, contract_hash)
        record = self.state_store.get(identity.__dict__)
        if engine.kind == "state_machine":
            key = self._identity_key(identity)
            controller = self._controllers.get(key)
            if controller is None:
                controller = StandaloneStateWorkController(
                    contract=contract, identity=identity.__dict__,
                    state_store=self.state_store, evidence_store=self.evidence_store,
                    evidence_registry=evidence_registry)
                self._controllers[key] = controller
                record = controller.inspect()
            snapshot = engine.inspect(identity, contract,
                                      {"state": record.get("state")},
                                      int(record.get("revision", 0) or 0))
        else:
            initial = engine.initialize(identity, contract)
            record = self.state_store.initialize_workflow(
                identity.__dict__, engine_kind=engine.kind, initial_data=initial)
            data = record.get("workflow_data") or initial
            snapshot = engine.inspect(identity, contract, data,
                                      int(record.get("revision", 0) or 0))
        return engine, contract, snapshot

    def inspect_workflow(self, identity: WorkflowIdentity | Mapping[str, Any], *,
                         contract_hash: str) -> WorkflowSnapshot:
        identity = self._identity(identity)
        _engine, _contract, snapshot = self._engine_snapshot(identity, contract_hash)
        return snapshot

    def eligible_steps(self, identity: WorkflowIdentity | Mapping[str, Any], *,
                       contract_hash: str) -> tuple[Any, ...]:
        return self.inspect_workflow(identity, contract_hash=contract_hash).eligible_steps

    def resolve_legacy_step(self, identity: WorkflowIdentity | Mapping[str, Any], *,
                            contract_hash: str, to_state: str,
                            trigger: Optional[str]) -> str:
        identity = self._identity(identity)
        engine, contract, snapshot = self._engine_snapshot(identity, contract_hash)
        if not isinstance(engine, StateMachineWorkflowEngine):
            raise TransitionError("legacy state transition API is only available for state_machine")
        return engine.resolve_legacy_step(
            contract, current_state=str(snapshot.current_state),
            to_state=to_state, trigger=trigger)

    def apply_step(self, identity: WorkflowIdentity | Mapping[str, Any], *,
                   contract_hash: str, step_id: str, evidence_refs: Iterable[str],
                   expected_revision: int) -> WorkflowDecision:
        identity = self._identity(identity)
        engine, contract, snapshot = self._engine_snapshot(identity, contract_hash)
        if snapshot.revision != int(expected_revision):
            raise TransitionError(
                f"workflow revision conflict: expected {expected_revision}, "
                f"found {snapshot.revision}; re-inspect required")
        references = list(evidence_refs)
        evidence = self.evidence_store.resolve(references)
        decision = engine.apply(identity, contract, snapshot,
                                step_id=step_id, evidence=evidence)
        if not decision.allowed:
            return decision
        if engine.kind == "state_machine":
            edge = next(item for item in contract.get("transitions") or ()
                        if item.get("id") == step_id)
            key = self._identity_key(identity)
            controller = self._controllers[key]
            committed = controller.request_transition(
                to_state=str(edge["to"]), trigger=str(edge.get("trigger") or ""),
                evidence_refs=references, expected_revision=expected_revision)
            if not committed.allowed:
                return WorkflowDecision(
                    False, committed.reason, engine.kind, step_id,
                    expected_revision, expected_revision,
                    str(committed.work_class or edge.get("work_class") or "workflow"),
                    str(committed.domain_effect or edge.get("domain_effect") or "workflow_state"),
                    str(committed.progress_class), snapshot.current_state,
                    snapshot.current_state, snapshot.completed, tuple(references),
                    {"state": snapshot.current_state})
            return decision
        try:
            committed = self.state_store.commit_workflow(
                identity.__dict__, expected_revision=expected_revision,
                engine_kind=engine.kind, workflow_data=decision.state_data,
                transition=decision.to_dict())
        except TransitionError:
            raise
        return WorkflowDecision(
            decision.allowed, decision.reason, decision.engine_kind, decision.step_id,
            expected_revision, int(committed["revision"]), decision.work_class,
            decision.domain_effect, decision.progress_class, decision.current_state,
            decision.previous_state, decision.completed, decision.evidence_refs,
            decision.state_data)

    @staticmethod
    def progress_fact(identity: WorkflowIdentity | Mapping[str, Any],
                      decision: WorkflowDecision) -> WorkflowProgressFact:
        identity = WorkflowAuthority._identity(identity)
        return WorkflowProgressFact(
            statework_id=identity.statework_id, subject_ref=identity.subject_ref,
            engine_kind=decision.engine_kind, step_id=decision.step_id,
            revision=decision.revision, progress_class=decision.progress_class,
            completed=decision.completed, evidence_refs=decision.evidence_refs)
