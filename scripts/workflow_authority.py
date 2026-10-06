"""Workflow selection and authority over legal StateWork activation."""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Iterable, Mapping, Optional

if __package__:
    from .errors import TransitionError
    from .evidence import EvidenceStore
    from .resources import ROOT, _aware_datetime, _load_yaml
    from .selection_store import WorkflowSelectionStore
    from .state_store import SubjectStateStore
    from .transition_engine import TransitionEngine
    from .workflow_controller import StandaloneStateWorkController
    from .workflow_engines import (EngineRegistry, MilestoneWorkflowEngine,
                                   StateMachineWorkflowEngine, WorkflowDecision,
                                   WorkflowIdentity, WorkflowProgressFact,
                                   WorkflowSnapshot, active_fact_ids,
                                   terminal_required_facts)
    from .composition_rules import depends_on, validate_selection
else:
    from errors import TransitionError
    from evidence import EvidenceStore
    from resources import ROOT, _aware_datetime, _load_yaml
    from selection_store import WorkflowSelectionStore
    from state_store import SubjectStateStore
    from transition_engine import TransitionEngine
    from workflow_controller import StandaloneStateWorkController
    from workflow_engines import (EngineRegistry, MilestoneWorkflowEngine,
                                  StateMachineWorkflowEngine, WorkflowDecision,
                                  WorkflowIdentity, WorkflowProgressFact,
                                  WorkflowSnapshot, active_fact_ids,
                                  terminal_required_facts)
    from composition_rules import depends_on, validate_selection


WORKFLOW_PORT_VERSION = "1.4.0"


@dataclass(frozen=True)
class WorkflowAuthorityIdentity:
    """Stable, immutable identity for one CSW workflow scope and contract."""

    namespace_id: str
    application_id: str
    application_instance_id: str
    workflow_id: str
    subject_ref: str
    registry_hash: str
    authority_instance_id: str
    storage_identity: str
    contract_version: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 512:
                raise ValueError(f"workflow authority identity {name} is invalid")

    def to_dict(self) -> Mapping[str, str]:
        return MappingProxyType({name: getattr(self, name)
                                 for name in self.__dataclass_fields__})


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
                 selection_store: Optional[WorkflowSelectionStore] = None,
                 storage_identity: Optional[Mapping[str, str]] = None):
        self.root = Path(root or ROOT)
        self.state_store = state_store or SubjectStateStore(
            self.root / "state" / "subjects.json")
        self.evidence_store = evidence_store or EvidenceStore()
        self.engine_registry = engine_registry or EngineRegistry()
        self.selection_store = selection_store or WorkflowSelectionStore(
            self.root / "state" / "workflow-selections.json")
        storage = dict(storage_identity or {})
        if not storage:
            evidence_store_identity = getattr(
                self.evidence_store, "_workflow_authority_storage_id", None)
            if not isinstance(evidence_store_identity, str):
                evidence_store_identity = "memory:" + secrets.token_hex(16)
                try:
                    setattr(self.evidence_store, "_workflow_authority_storage_id",
                            evidence_store_identity)
                except (AttributeError, TypeError):
                    evidence_store_identity = (
                        f"opaque:{type(self.evidence_store).__module__}."
                        f"{type(self.evidence_store).__qualname__}")
            storage = {
                "state_store": str(Path(self.state_store.path).resolve()),
                "selection_store": str(Path(self.selection_store.path).resolve()),
                "evidence_store": evidence_store_identity,
            }
        if (not storage or len(storage) > 16
                or any(not isinstance(key, str) or not key or len(key) > 64
                       or not isinstance(value, str) or not value or len(value) > 1024
                       for key, value in storage.items())):
            raise ValueError("workflow authority storage identity is malformed")
        self.storage_components = MappingProxyType(dict(sorted(storage.items())))
        storage_payload = json.dumps(dict(self.storage_components), sort_keys=True,
                                     separators=(",", ":"))
        self.storage_identity = "csw-storage:" + hashlib.sha256(
            storage_payload.encode("utf-8")).hexdigest()
        self._controllers: Dict[str, StandaloneStateWorkController] = {}
        # Bundle contracts are verified once against the pinned compiled
        # registry. Snapshot calls can then reuse parsed engine definitions
        # without reopening every source YAML file.
        self._bundle_cache: Dict[str, tuple[dict[str, Any], dict[str, Any],
                                            str, Any, dict[str, Any]]] = {}
        # The registry is a process-lifetime trust pin. Authority calls never
        # re-read it implicitly, so one request cannot mix registry versions.
        self._compiled_registry = load_compiled_registry(self.root)
        self._registry_hash = str(self._compiled_registry["registry_hash"])
        self.authority_instance_id = self._authority_instance_id(self._registry_hash)

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
        self.authority_instance_id = self._authority_instance_id(actual)
        self._controllers.clear()
        self._bundle_cache.clear()
        return actual

    def _authority_instance_id(self, registry_hash: str) -> str:
        basis = json.dumps({
            "root": str(self.root.resolve()),
            "registry_hash": registry_hash,
            "storage_identity": self.storage_identity,
            "workflow_port_version": self.workflow_port_version,
        }, sort_keys=True, separators=(",", ":"))
        return "csw-authority:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()

    def checkpoint_selection(self, *, workflow_scope: Mapping[str, Any],
                             tick_id: str, expected_selection_revision: int) -> None:
        self.selection_store.create_checkpoint(
            workflow_scope, tick_id=tick_id,
            expected_revision=expected_selection_revision)

    def restore_selection_checkpoint(self, *, workflow_scope: Mapping[str, Any],
                                     tick_id: str,
                                     expected_selection_revision: int
                                     ) -> Optional[dict[str, Any]]:
        return self.selection_store.restore_checkpoint(
            workflow_scope, tick_id=tick_id,
            expected_revision=expected_selection_revision)

    def finalize_selection_checkpoint(self, *, workflow_scope: Mapping[str, Any],
                                      tick_id: str) -> None:
        self.selection_store.finalize_checkpoint(workflow_scope, tick_id=tick_id)

    def _bundle(self, statework_id: str, contract_hash: Optional[str] = None
                ) -> tuple[dict[str, Any], dict[str, Any], str, Any, dict[str, Any]]:
        compiled = self._compiled_registry
        entry = next((item for item in compiled.get("stateworks") or ()
                      if item.get("id") == statework_id), None)
        if entry is None:
            raise TransitionError(f"StateWork {statework_id!r} is unavailable")
        cached = self._bundle_cache.get(statework_id)
        if cached is not None:
            manifest, contract, digest, engine, evidence_registry = cached
            if contract_hash and contract_hash != digest:
                raise TransitionError("workflow contract differs from the CFW policy pin")
            return (dict(manifest), dict(contract), digest, engine,
                    dict(evidence_registry))
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
        self._bundle_cache[statework_id] = (
            dict(manifest), dict(contract), digest, engine,
            dict(evidence_registry))
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

    def workflow_authority_identity(
            self, identity: WorkflowIdentity | Mapping[str, Any], *,
            contract_hash: str) -> WorkflowAuthorityIdentity:
        """Return the stable core identity for a registered workflow scope."""
        workflow_identity = self._identity(identity)
        contract = self.workflow_contract_identity(
            workflow_identity.statework_id, contract_hash)
        if (workflow_identity.contract_version != contract["contract_version"]
                or contract["contract_hash"] != contract_hash):
            raise TransitionError("workflow authority identity differs from its contract pin")
        return WorkflowAuthorityIdentity(
            namespace_id=workflow_identity.namespace_id,
            application_id=workflow_identity.application_id,
            application_instance_id=workflow_identity.application_instance_id,
            workflow_id=workflow_identity.workflow_id,
            subject_ref=workflow_identity.subject_ref,
            registry_hash=self.registry_hash,
            authority_instance_id=self.authority_instance_id,
            storage_identity=self.storage_identity,
            contract_version=workflow_identity.contract_version,
        )

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

    @staticmethod
    def _fact_ids(contract: Mapping[str, Any]) -> set[str]:
        facts = contract.get("facts", {})
        if facts is None:
            facts = {}
        if not isinstance(facts, Mapping):
            raise TransitionError("workflow fact declarations are malformed")
        return set(facts)

    def _initial_fact_ledger(self, contract: Mapping[str, Any]
                             ) -> list[dict[str, Any]]:
        return [{"fact_id": fact_id, "status": "UNKNOWN",
                 "established_revision": None, "evidence_refs": [],
                 "invalidated_by": []}
                for fact_id in sorted(self._fact_ids(contract))]

    def _normalize_fact_ledger(
            self, contract: Mapping[str, Any], value: Any
            ) -> list[dict[str, Any]]:
        if value is None:
            value = self._initial_fact_ledger(contract)
        if isinstance(value, Mapping):
            value = list(value.values())
        if not isinstance(value, (list, tuple)) or len(value) > 64:
            raise TransitionError("workflow fact ledger is malformed or oversized")
        facts = self._fact_ids(contract)
        ledger: dict[str, dict[str, Any]] = {}
        for raw in value:
            if not isinstance(raw, Mapping) or set(raw) != {
                    "fact_id", "status", "established_revision",
                    "evidence_refs", "invalidated_by"}:
                raise TransitionError("workflow fact ledger entry is malformed")
            fact_id = raw["fact_id"]
            status = raw["status"]
            established_revision = raw["established_revision"]
            evidence_refs = raw["evidence_refs"]
            invalidated_by = raw["invalidated_by"]
            if (not isinstance(fact_id, str) or fact_id not in facts
                    or fact_id in ledger
                    or not isinstance(status, str)
                    or status not in {"UNKNOWN", "ESTABLISHED", "INVALIDATED"}
                    or (established_revision is not None
                        and (type(established_revision) is not int
                             or established_revision < 1))
                    or not isinstance(evidence_refs, (list, tuple))
                    or len(evidence_refs) > 128
                    or any(not isinstance(ref, str) or not ref or len(ref) > 256
                           for ref in evidence_refs)
                    or len(evidence_refs) != len(set(evidence_refs))
                    or not isinstance(invalidated_by, (list, tuple))
                    or len(invalidated_by) > 64
                    or any(not isinstance(item, str) or not item or len(item) > 320
                           for item in invalidated_by)
                    or len(invalidated_by) != len(set(invalidated_by))):
                raise TransitionError("workflow fact ledger fields are invalid")
            if ((status == "UNKNOWN" and
                 (established_revision is not None or evidence_refs or invalidated_by))
                    or (status == "ESTABLISHED" and established_revision is None)
                    or (status == "INVALIDATED" and not invalidated_by)):
                raise TransitionError("workflow fact ledger status is inconsistent")
            ledger[fact_id] = {
                "fact_id": fact_id, "status": status,
                "established_revision": established_revision,
                "evidence_refs": list(evidence_refs),
                "invalidated_by": list(invalidated_by),
            }
        for fact_id in facts - set(ledger):
            ledger[fact_id] = self._initial_fact_ledger({"facts": {fact_id: {}}})[0]
        return [ledger[fact_id] for fact_id in sorted(ledger)]

    def _validated_fact_effects(
            self, contract: Mapping[str, Any], effects: Mapping[str, Any]
            ) -> dict[str, list[str]]:
        known = self._fact_ids(contract)
        normalized: dict[str, list[str]] = {}
        for name in ("requires_facts", "establishes_facts", "invalidates_facts"):
            values = effects.get(name, ())
            if values is None:
                values = ()
            if (not isinstance(values, (list, tuple)) or len(values) > 64
                    or any(not isinstance(value, str) or not value or len(value) > 128
                           for value in values)
                    or len(values) != len(set(values))
                    or set(values) - known):
                raise TransitionError(f"workflow {name} are malformed")
            normalized[name] = list(values)
        if set(normalized["establishes_facts"]) & set(normalized["invalidates_facts"]):
            raise TransitionError("a workflow step cannot establish and invalidate the same fact")
        return normalized

    def _refresh_fact_ledger(self, identity: WorkflowIdentity,
                             contract: Mapping[str, Any], value: Any
                             ) -> list[dict[str, Any]]:
        ledger = self._normalize_fact_ledger(contract, value)
        for entry in ledger:
            if entry["status"] != "ESTABLISHED" or not entry["evidence_refs"]:
                continue
            refs = entry["evidence_refs"]
            try:
                records = self.evidence_store.resolve(refs)
            except TransitionError:
                records = []
            invalid_refs = set(refs)
            if records:
                invalid_refs = {
                    str(record.get("ref") or "") for record in records
                    if (record.get("invalidated") is True
                        or record.get("subject_ref") != identity.subject_ref)
                }
            if invalid_refs:
                causes = {f"evidence:{ref}" for ref in invalid_refs if ref}
                entry["status"] = "INVALIDATED"
                entry["invalidated_by"] = sorted(
                    set(entry["invalidated_by"]) | causes)
        return ledger

    def _apply_fact_effects(
            self, identity: WorkflowIdentity, contract: Mapping[str, Any],
            value: Any, effects: Mapping[str, Any], *, revision: int,
            evidence_refs: Iterable[str], step_id: str
            ) -> list[dict[str, Any]]:
        normalized = self._validated_fact_effects(contract, effects)
        ledger = {entry["fact_id"]: entry for entry in
                  self._normalize_fact_ledger(contract, value)}
        active_before = {fact_id for fact_id, entry in ledger.items()
                         if entry["status"] == "ESTABLISHED"}
        required = set(normalized["requires_facts"])
        refs = list(evidence_refs)
        requirements_met = required.issubset(active_before)
        for fact_id in normalized["invalidates_facts"]:
            entry = ledger[fact_id]
            entry["status"] = "INVALIDATED"
            entry["invalidated_by"] = sorted(
                set(entry["invalidated_by"]) | {step_id})
        for fact_id in normalized["establishes_facts"]:
            entry = ledger[fact_id]
            if requirements_met:
                ledger[fact_id] = {
                    "fact_id": fact_id, "status": "ESTABLISHED",
                    "established_revision": revision,
                    "evidence_refs": refs,
                    "invalidated_by": [],
                }
            else:
                missing = sorted(required - active_before)
                ledger[fact_id] = {
                    "fact_id": fact_id, "status": "INVALIDATED",
                    "established_revision": revision,
                    "evidence_refs": refs,
                    "invalidated_by": [f"fact:{item}" for item in missing],
                }
        return self._refresh_fact_ledger(identity, contract,
                                         [ledger[key] for key in sorted(ledger)])

    def _step_fact_effects(
            self, engine: Any, contract: Mapping[str, Any], step_id: str,
            decision: WorkflowDecision
            ) -> dict[str, list[str]]:
        field = "transitions" if engine.kind == "state_machine" else "steps"
        rows = contract.get(field) or ()
        row = next((item for item in rows if item.get("id") == step_id), None)
        if row is not None:
            raw = {name: row.get(name) or () for name in (
                "requires_facts", "establishes_facts", "invalidates_facts")}
        else:
            raw = {"requires_facts": decision.requires_facts,
                   "establishes_facts": decision.establishes_facts,
                   "invalidates_facts": decision.invalidates_facts}
        return self._validated_fact_effects(contract, raw)

    @staticmethod
    def _state_machine_freshness_error(
            edge: Mapping[str, Any], evidence: Iterable[Mapping[str, Any]], *,
            state_entered_at: Optional[str]) -> Optional[str]:
        freshness = edge.get("evidence_freshness") or {}
        required = set(edge.get("required_evidence") or ())
        relevant = [item for item in evidence if item.get("kind") in required]
        if freshness.get("mode") == "after_state_entry" and state_entered_at:
            try:
                entered_at = _aware_datetime(state_entered_at)
                if any(_aware_datetime(item.get("observed_at")) < entered_at
                       for item in relevant):
                    return "evidence predates current state entry"
            except ValueError as exc:
                return str(exc)
        max_age = freshness.get("max_age_seconds")
        if max_age is not None:
            now = datetime.now(timezone.utc)
            for item in relevant:
                try:
                    observed = _aware_datetime(item.get("observed_at"))
                except ValueError as exc:
                    return str(exc)
                if (now - observed).total_seconds() > int(max_age):
                    return "evidence exceeds declared freshness"
        return None

    def _invalidate_fact_establishments(
            self, contract: Mapping[str, Any], value: Any,
            effects: Mapping[str, Any], *, revision: int,
            evidence_refs: Iterable[str], step_id: str,
            missing_facts: Iterable[str] = (),
            invalidation_causes: Iterable[str] = (),
            evidence_invalidated: bool = True) -> list[dict[str, Any]]:
        ledger = {entry["fact_id"]: entry for entry in
                  self._normalize_fact_ledger(contract, value)}
        refs = list(evidence_refs)
        causes = ({f"evidence:{ref}" for ref in refs}
                  if evidence_invalidated else set())
        causes.update(f"fact:{fact_id}" for fact_id in missing_facts)
        causes.update(str(cause) for cause in invalidation_causes)
        if not causes:
            causes.add(f"transition:{step_id}")
        for fact_id in effects.get("establishes_facts") or ():
            ledger[fact_id] = {
                "fact_id": fact_id, "status": "INVALIDATED",
                "established_revision": revision,
                "evidence_refs": refs,
                "invalidated_by": sorted(causes),
            }
        return [ledger[key] for key in sorted(ledger)]

    def _snapshot_with_fact_ledger(
            self, snapshot: WorkflowSnapshot, contract: Mapping[str, Any],
            fact_ledger: list[dict[str, Any]]) -> WorkflowSnapshot:
        data = dict(snapshot.data)
        if fact_ledger:
            data["fact_ledger"] = fact_ledger
        active = active_fact_ids(data)
        eligible = tuple(step for step in snapshot.eligible_steps
                         if set(step.requires_facts).issubset(active))
        completed = (snapshot.completed
                     and terminal_required_facts(contract).issubset(active))
        return WorkflowSnapshot(snapshot.identity, snapshot.engine_kind,
                                snapshot.revision, data, snapshot.current_state,
                                completed, eligible)

    def _recompute_milestone_fact_ledger(
            self, identity: WorkflowIdentity, contract: Mapping[str, Any],
            workflow_data: Mapping[str, Any], workflow_revision: int
            ) -> list[dict[str, Any]]:
        ledger, _completed = self._recompute_milestone_projection(
            identity, contract, workflow_data, workflow_revision)
        return ledger

    def _recompute_milestone_projection(
            self, identity: WorkflowIdentity, contract: Mapping[str, Any],
            workflow_data: Mapping[str, Any], workflow_revision: int
            ) -> tuple[list[dict[str, Any]], list[str]]:
        receipts = workflow_data.get("milestone_receipts") or ()
        if not isinstance(receipts, (list, tuple)) or len(receipts) > 4096:
            raise TransitionError("milestone receipt ledger is malformed or oversized")
        steps = {str(item.get("id")): item
                 for item in contract.get("steps") or ()}
        latest: dict[str, tuple[int, list[str], dict[str, list[str]]]] = {}
        previous_revision = 0
        for raw in receipts:
            receipt_fields = {"step_id", "evidence_refs", "workflow_revision"}
            effect_fields = {"requires_facts", "establishes_facts", "invalidates_facts"}
            if (not isinstance(raw, Mapping)
                    or not receipt_fields.issubset(raw)
                    or set(raw) - receipt_fields - effect_fields):
                raise TransitionError("milestone receipt is malformed")
            step_id, refs, revision = (raw.get("step_id"),
                                       raw.get("evidence_refs"),
                                       raw.get("workflow_revision"))
            if (not isinstance(step_id, str) or step_id not in steps
                    or not isinstance(refs, (list, tuple)) or len(refs) > 128
                    or any(not isinstance(ref, str) or not ref or len(ref) > 256
                           for ref in refs)
                    or len(refs) != len(set(refs))
                    or type(revision) is not int or revision <= previous_revision
                    or revision > workflow_revision):
                raise TransitionError("milestone receipt fields are invalid")
            previous_revision = revision
            step = steps[step_id]
            declared_effects = {name: step.get(name) or () for name in (
                "requires_facts", "establishes_facts", "invalidates_facts")}
            effects = {name: raw.get(name, declared_effects[name]) for name in (
                "requires_facts", "establishes_facts", "invalidates_facts")}
            effects = self._validated_fact_effects(contract, effects)
            declared_effects = self._validated_fact_effects(contract, declared_effects)
            if effects != declared_effects:
                raise TransitionError("milestone receipt fact effects differ from contract")
            latest[step_id] = (revision, list(refs), effects)

        ledger = self._initial_fact_ledger(contract)
        completed: set[str] = set()
        for step_id in MilestoneWorkflowEngine._topological_order(
                list(steps.values())):
            receipt = latest.get(step_id)
            if receipt is None:
                continue
            revision, refs, effects = receipt
            step = steps[step_id]
            missing_dependencies = set(step.get("depends_on") or ()) - completed
            missing_facts = (set(effects["requires_facts"])
                             - active_fact_ids({"fact_ledger": ledger}))
            try:
                evidence = self.evidence_store.resolve(refs) if refs else []
            except TransitionError:
                evidence = []
            evidence_valid = (len(evidence) == len(refs)
                              and all(item.get("invalidated") is not True
                                      and item.get("subject_ref") == identity.subject_ref
                                      for item in evidence))
            required_kinds = set(step.get("required_evidence") or ())
            found_kinds = {str(item.get("kind") or "") for item in evidence}
            evidence_valid = (evidence_valid
                              and required_kinds.issubset(found_kinds))
            if not missing_dependencies and not missing_facts and evidence_valid:
                ledger = self._apply_fact_effects(
                    identity, contract, ledger, effects, revision=revision,
                    evidence_refs=refs, step_id=step_id)
                completed.add(step_id)
            else:
                ledger = self._invalidate_fact_establishments(
                    contract, ledger, effects, revision=revision,
                    evidence_refs=refs, step_id=step_id,
                    missing_facts=missing_facts,
                    evidence_invalidated=not evidence_valid,
                    invalidation_causes=(f"step:{item}"
                                         for item in sorted(missing_dependencies)))
        return (self._refresh_fact_ledger(identity, contract, ledger),
                sorted(completed))

    def _engine_snapshot(self, identity: WorkflowIdentity, contract_hash: str
                         ) -> tuple[Any, dict[str, Any], WorkflowSnapshot]:
        evidence_storage = self.storage_components.get("evidence_store")
        if (isinstance(evidence_storage, str)
                and not evidence_storage.startswith(("memory:", "opaque:"))):
            self.evidence_store.refresh_attested(Path(evidence_storage))
        manifest, contract, _digest, engine, evidence_registry = self._bundle(
            identity.statework_id, contract_hash)
        record = self.state_store.get(identity.__dict__)
        fact_ledger: list[dict[str, Any]] = []
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
            current_state, record, fact_ledger = self._recompute_state_machine_state(
                identity, contract, engine, record)
            snapshot = engine.inspect(identity, contract,
                                      {"state": current_state,
                                       "fact_ledger": fact_ledger},
                                      int(record.get("revision", 0) or 0))
        else:
            initial = engine.initialize(identity, contract)
            record = self.state_store.initialize_workflow(
                identity.__dict__, engine_kind=engine.kind, initial_data=initial)
            data = dict(record.get("workflow_data") or initial)
            if self._fact_ids(contract):
                if engine.kind == "milestone":
                    fact_ledger = self._recompute_milestone_fact_ledger(
                        identity, contract, data,
                        int(record.get("revision", 0) or 0))
                else:
                    fact_ledger = self._refresh_fact_ledger(
                        identity, contract, data.get("fact_ledger"))
                if data.get("fact_ledger") != fact_ledger:
                    data["fact_ledger"] = fact_ledger
                    record = self.state_store.commit_workflow(
                        identity.__dict__,
                        expected_revision=int(record.get("revision", 0) or 0),
                        engine_kind=engine.kind, workflow_data=data,
                        transition={"trigger": "workflow_fact_reconcile",
                                    "fact_ledger": fact_ledger})
            if engine.kind == "milestone":
                data["completed_steps"] = self._valid_milestone_completions(
                    identity, contract, data, int(record.get("revision", 0) or 0))
            snapshot = engine.inspect(identity, contract, data,
                                      int(record.get("revision", 0) or 0))
        snapshot = self._snapshot_with_fact_ledger(snapshot, contract, fact_ledger)
        return engine, contract, snapshot

    def _state_machine_history(self, identity: WorkflowIdentity
                               ) -> list[dict[str, Any]]:
        """Read bounded append-only events for one state-machine identity."""
        read_history = getattr(self.state_store, "history_for", None)
        if not callable(read_history):
            raise TransitionError("state-machine history is unavailable")
        try:
            events = read_history(identity.__dict__, maximum=4096)
        except Exception as exc:
            raise TransitionError("state-machine history is unreadable") from exc
        if not isinstance(events, (list, tuple)) or len(events) > 4096:
            raise TransitionError("state-machine history exceeds its inspection bound")
        normalized: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, Mapping):
                raise TransitionError("state-machine history event is malformed")
            normalized.append(dict(event))
        return normalized

    def _recompute_state_machine_state(
            self, identity: WorkflowIdentity, contract: Mapping[str, Any],
            engine: StateMachineWorkflowEngine, record: Mapping[str, Any]
            ) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
        """Replay state and fact effects against current authoritative evidence."""
        revision = record.get("revision", 0)
        if type(revision) is not int or revision < 0:
            raise TransitionError("state-machine revision is malformed")
        events = self._state_machine_history(identity)
        if len(events) != revision:
            raise TransitionError("state-machine history does not match its current revision")

        current = str(contract["initial_state"])
        supported_transition_changed = False
        unsupported_refs: set[str] = set()
        fact_ledger = self._initial_fact_ledger(contract)
        state_updated_at: Optional[str] = None
        expected_identity = dict(identity.__dict__)
        transition_engine = getattr(engine, "_transition_engine", None)
        if transition_engine is None:
            raise TransitionError("state-machine transition validator is unavailable")

        for index, event in enumerate(events, start=1):
            event_identity = event.get("identity")
            event_revision = event.get("revision")
            transition = event.get("transition")
            if (event_identity != expected_identity or type(event_revision) is not int
                    or event_revision != index or not isinstance(transition, Mapping)):
                raise TransitionError("state-machine history event is inconsistent")
            event_recorded_at = event.get("recorded_at")
            if event_recorded_at is not None:
                try:
                    _aware_datetime(event_recorded_at)
                except ValueError as exc:
                    raise TransitionError("state-machine history timestamp is invalid") from exc
            prior_updated_at = state_updated_at
            state_updated_at = event_recorded_at
            trigger = transition.get("trigger")
            if trigger == "controller_initialization":
                if (index != 1 or event.get("from_state") is not None
                        or event.get("to_state") != current):
                    raise TransitionError("state-machine initialization history is inconsistent")
                continue
            if trigger == "evidence_supported_state_reconcile":
                reconciled_state = transition.get("reconciled_state")
                if (not isinstance(reconciled_state, str)
                        or reconciled_state != current
                        or event.get("to_state") != current):
                    raise TransitionError("state-machine reconciliation history is inconsistent")
                continue

            # Later events can depend on a now-invalid transition. They no
            # longer apply when their recorded origin is absent from the
            # evidence-supported path.
            if event.get("from_state") != current:
                continue
            target = event.get("to_state")
            refs = transition.get("evidence_refs") or ()
            if (not isinstance(target, str) or target not in set(contract.get("states") or ())
                    or not isinstance(refs, (tuple, list)) or len(refs) > 128
                    or any(not isinstance(ref, str) or not ref or len(ref) > 256
                           for ref in refs)
                    or len(refs) != len(set(refs))):
                raise TransitionError("state-machine transition history is malformed")
            edge_id = None
            progress = transition.get("progress")
            if isinstance(progress, Mapping):
                edge_id = progress.get("edge_id")
            matching_edges = transition_engine.matching_edges(
                current, target, trigger if isinstance(trigger, str) else None)
            if edge_id is not None:
                matching_edges = [edge for edge in matching_edges
                                  if edge.get("id") == edge_id]
            if len(matching_edges) != 1:
                raise TransitionError("state-machine history no longer matches its contract")

            try:
                evidence = self.evidence_store.resolve(refs) if refs else []
            except TransitionError:
                evidence = []
            step_id = str(matching_edges[0]["id"])
            effects = self._step_fact_effects(engine, contract, step_id,
                                              WorkflowDecision(
                                                  True, "history replay", engine.kind,
                                                  step_id, index - 1, index, "workflow",
                                                  "workflow_state", "LATERAL", current,
                                                  current, False))
            recorded_effects = transition.get("fact_effects")
            if recorded_effects is not None:
                if not isinstance(recorded_effects, Mapping):
                    raise TransitionError("state-machine fact effects are malformed")
                recorded_effects = self._validated_fact_effects(
                    contract, recorded_effects)
                if recorded_effects != effects:
                    raise TransitionError("state-machine fact effects differ from contract")
            replay_snapshot = WorkflowSnapshot(
                identity, engine.kind, index - 1,
                {"state": current, "fact_ledger": fact_ledger}, current,
                (current in set(contract.get("completion_states") or ())
                 and terminal_required_facts(contract).issubset(
                     active_fact_ids({"fact_ledger": fact_ledger}))))
            decision = engine.apply(
                identity, contract, replay_snapshot, step_id=step_id, evidence=evidence)
            freshness_error = self._state_machine_freshness_error(
                matching_edges[0], evidence, state_entered_at=prior_updated_at)
            transition_supported = decision.allowed and freshness_error is None
            if transition_supported:
                fact_ledger = self._apply_fact_effects(
                    identity, contract, fact_ledger, effects, revision=index,
                    evidence_refs=refs, step_id=step_id)
                current = target
                continue

            supported_transition_changed = True
            unsupported_refs.update(refs)
            missing_facts = (set(effects["requires_facts"])
                             - active_fact_ids({"fact_ledger": fact_ledger}))
            required_kinds = set(matching_edges[0].get("required_evidence") or ())
            found_kinds = {str(item.get("kind") or "") for item in evidence}
            evidence_invalidated = (
                len(evidence) != len(refs)
                or any(item.get("invalidated") is True
                       or item.get("subject_ref") != identity.subject_ref
                       for item in evidence)
                or not required_kinds.issubset(found_kinds)
                or freshness_error is not None)
            fact_ledger = self._invalidate_fact_establishments(
                contract, fact_ledger, effects, revision=index,
                evidence_refs=refs, step_id=step_id,
                missing_facts=missing_facts,
                evidence_invalidated=evidence_invalidated)

        stored_state = record.get("state")
        stored_fact_ledger = record.get("fact_ledger")
        ledger_changed = bool(self._fact_ids(contract)) and stored_fact_ledger != fact_ledger
        if stored_state != current and not supported_transition_changed:
            raise TransitionError(
                "stored state differs from its evidence-supported transition history")
        if stored_state != current or ledger_changed:
            corrected = self.state_store.commit(
                identity.__dict__, expected_revision=revision, new_state=current,
                fact_ledger=fact_ledger,
                transition={
                    "trigger": "evidence_supported_state_reconcile",
                    "reconciled_state": current,
                    "unsupported_transition_evidence_refs": sorted(unsupported_refs),
                })
            return current, corrected, fact_ledger
        return current, dict(record), fact_ledger

    def _valid_milestone_completions(
            self, identity: WorkflowIdentity, contract: Mapping[str, Any],
            workflow_data: Mapping[str, Any], workflow_revision: int) -> list[str]:
        """Project valid milestone receipts from current evidence and facts."""
        _ledger, completed = self._recompute_milestone_projection(
            identity, contract, workflow_data, workflow_revision)
        return completed

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
        if (len(references) > 128
                or any(not isinstance(ref, str) or not ref or len(ref) > 256
                       for ref in references)
                or len(references) != len(set(references))):
            raise TransitionError("workflow evidence references are malformed")
        evidence = self.evidence_store.resolve(references)
        if engine.kind == "milestone" and any(
                item.get("invalidated") is True
                or item.get("subject_ref") != identity.subject_ref
                for item in evidence):
            raise TransitionError(
                "milestones require current evidence scoped to the workflow subject")
        decision = engine.apply(identity, contract, snapshot,
                                step_id=step_id, evidence=evidence)
        if not decision.allowed:
            return decision
        effects = self._step_fact_effects(engine, contract, step_id, decision)
        missing_facts = set(effects["requires_facts"]) - active_fact_ids(snapshot.data)
        if missing_facts:
            return WorkflowDecision(
                False, "required workflow facts are not established", engine.kind,
                step_id, expected_revision, expected_revision,
                decision.work_class, decision.domain_effect, "LATERAL",
                decision.previous_state, decision.previous_state,
                snapshot.completed, tuple(references), dict(snapshot.data),
                requires_facts=tuple(effects["requires_facts"]))
        if engine.kind == "state_machine":
            edge = next(item for item in contract.get("transitions") or ()
                        if item.get("id") == step_id)
            current_record = self.state_store.get(identity.__dict__)
            if (int(current_record.get("revision", 0) or 0) != expected_revision
                    or current_record.get("state") != snapshot.current_state):
                raise TransitionError(
                    "state-machine changed during workflow application; re-inspect required")
            freshness_error = self._state_machine_freshness_error(
                edge, evidence, state_entered_at=current_record.get("updated_at"))
            if freshness_error:
                return WorkflowDecision(
                    False, freshness_error, engine.kind, step_id,
                    expected_revision, expected_revision,
                    str(edge.get("work_class") or "workflow"),
                    str(edge.get("domain_effect") or "workflow_state"),
                    "LATERAL", snapshot.current_state,
                    snapshot.current_state, snapshot.completed, tuple(references),
                    dict(snapshot.data), requires_facts=tuple(effects["requires_facts"]))
            next_ledger = self._apply_fact_effects(
                identity, contract, snapshot.data.get("fact_ledger"), effects,
                revision=expected_revision + 1, evidence_refs=references,
                step_id=step_id)
            state_data = {"state": decision.current_state,
                          "fact_ledger": next_ledger}
            transition = {
                "trigger": str(edge.get("trigger") or ""),
                "step_id": step_id,
                "evidence_refs": references,
                "decision_reason": decision.reason,
                "progress": {"edge_id": step_id,
                             "progress_class": decision.progress_class},
                "fact_effects": effects,
            }
            committed = self.state_store.commit(
                identity.__dict__, expected_revision=expected_revision,
                new_state=str(decision.current_state), transition=transition,
                fact_ledger=(next_ledger if self._fact_ids(contract) else None))
            completed = (decision.current_state in set(
                contract.get("completion_states") or ())
                and terminal_required_facts(contract).issubset(
                    active_fact_ids({"fact_ledger": next_ledger})))
            return WorkflowDecision(
                decision.allowed, decision.reason, decision.engine_kind,
                decision.step_id, expected_revision, int(committed["revision"]),
                decision.work_class, decision.domain_effect, decision.progress_class,
                decision.current_state, decision.previous_state, completed,
                decision.evidence_refs, state_data,
                requires_facts=decision.requires_facts,
                establishes_facts=decision.establishes_facts,
                invalidates_facts=decision.invalidates_facts)
        workflow_data = dict(decision.state_data)
        if self._fact_ids(contract):
            if engine.kind == "milestone":
                fact_ledger = self._recompute_milestone_fact_ledger(
                    identity, contract, workflow_data, expected_revision + 1)
            else:
                fact_ledger = self._apply_fact_effects(
                    identity, contract, snapshot.data.get("fact_ledger"), effects,
                    revision=expected_revision + 1, evidence_refs=references,
                    step_id=step_id)
            workflow_data["fact_ledger"] = fact_ledger
        transition = decision.to_dict()
        transition["fact_effects"] = effects
        try:
            committed = self.state_store.commit_workflow(
                identity.__dict__, expected_revision=expected_revision,
                engine_kind=engine.kind, workflow_data=workflow_data,
                transition=transition)
        except TransitionError:
            raise
        completed = decision.completed
        if engine.kind == "milestone":
            committed_snapshot = self.inspect_workflow(
                identity, contract_hash=contract_hash)
            completed = committed_snapshot.completed
            committed_revision = committed_snapshot.revision
        else:
            committed_revision = int(committed["revision"])
        return WorkflowDecision(
            decision.allowed, decision.reason, decision.engine_kind, decision.step_id,
            expected_revision, committed_revision, decision.work_class,
            decision.domain_effect, decision.progress_class, decision.current_state,
            decision.previous_state, completed, decision.evidence_refs,
            workflow_data, requires_facts=decision.requires_facts,
            establishes_facts=decision.establishes_facts,
            invalidates_facts=decision.invalidates_facts)

    @staticmethod
    def progress_fact(identity: WorkflowIdentity | Mapping[str, Any],
                      decision: WorkflowDecision) -> WorkflowProgressFact:
        identity = WorkflowAuthority._identity(identity)
        return WorkflowProgressFact(
            statework_id=identity.statework_id, subject_ref=identity.subject_ref,
            engine_kind=decision.engine_kind, step_id=decision.step_id,
            revision=decision.revision, progress_class=decision.progress_class,
            completed=decision.completed, evidence_refs=decision.evidence_refs)
