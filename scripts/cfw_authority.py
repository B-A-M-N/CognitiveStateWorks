"""CSW-owned adapter for the CFW StateAuthority protocol."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional


def _default_control_plane() -> Any:
    from . import control_plane
    return control_plane


class CFWAuthorityAdapter:
    """Concrete combined-mode adapter owned by CSW, injected into CFW."""
    def __init__(self, root: Path, *, control_plane_module: Any = None,
                 state_path: Optional[Path] = None,
                 evidence_path: Optional[Path] = None,
                 namespace_id: str = "default", application_id: str = "cognitiveframeworks-runtime",
                 application_instance_id: str = "cognitiveframeworks-runtime",
                 workflow_id: str = "default-workflow",
                 statework_memberships: Optional[Mapping[str, Mapping[str, Any]]] = None) -> None:
        self.root = Path(root)
        self.control = control_plane_module or _default_control_plane()
        self.compiled_registry = self.control.load_compiled_registry(self.root)
        self.state_store = self.control.SubjectStateStore(
            Path(state_path) if state_path else self.root / "state" / "subjects.json")
        self.evidence_store = self.control.EvidenceStore()
        self.evidence_path = Path(evidence_path) if evidence_path else self.root / "state" / "evidence.json"
        object.__setattr__(self, "namespace_id", str(namespace_id))
        object.__setattr__(self, "application_id", str(application_id))
        object.__setattr__(self, "application_instance_id", str(application_instance_id))
        object.__setattr__(self, "workflow_id", str(workflow_id))
        self.statework_memberships = {
            str(key): MappingProxyType(dict(value))
            for key, value in (statework_memberships or {}).items()}
        object.__setattr__(self, "_frozen_scope", True)
        self._controllers: Dict[str, Any] = {}
        self._load_evidence()
        self.workflow_authority = self.control.WorkflowAuthority(
            root=self.root, state_store=self.state_store,
            evidence_store=self.evidence_store)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_frozen_scope", False) and name in {
                "namespace_id", "application_id", "application_instance_id", "workflow_id"}:
            raise AttributeError("CSW authority scope is immutable")
        object.__setattr__(self, name, value)

    def bind_scope(self, *, namespace_id: str, application_id: str,
                   application_instance_id: str, workflow_id: str,
                   statework_memberships: Optional[Mapping[str, Mapping[str, Any]]] = None
                   ) -> "CFWAuthorityAdapter":
        """Return a task-scoped view while sharing durable storage services."""
        return CFWAuthorityAdapter(
            self.root, control_plane_module=self.control,
            state_path=self.state_store.path,
            evidence_path=self.evidence_path, namespace_id=namespace_id,
            application_id=application_id, application_instance_id=application_instance_id,
            workflow_id=workflow_id,
            statework_memberships=statework_memberships)

    def _load_evidence(self) -> None:
        if not self.evidence_path.exists():
            return
        try:
            records = json.loads(self.evidence_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("CSW evidence authority is unreadable") from exc
        if isinstance(records, list):
            self.evidence_store = self.control.EvidenceStore.load_attested(records)

    def _contract(self, statework_id: str, contract_hash: str) -> tuple[Dict[str, Any], str]:
        identity = self.workflow_authority.workflow_contract_identity(
            statework_id, contract_hash)
        return dict(identity["contract"]), str(identity["contract_hash"])

    def _workflow_identity(self, *, statework_id: str, subject_ref: str,
                           contract_hash: str) -> Any:
        contract_identity = self.workflow_authority.workflow_contract_identity(
            statework_id, contract_hash)
        membership = self.statework_memberships.get(statework_id) or {}
        if membership and membership.get("subject_ref") != subject_ref:
            raise PermissionError("workflow subject differs from its host membership binding")
        return self.control.WorkflowIdentity(
            namespace_id=str(membership.get("namespace_id") or self.namespace_id),
            application_id=str(membership.get("application_id") or self.application_id),
            application_instance_id=str(membership.get("application_instance_id")
                                        or self.application_instance_id),
            workflow_id=str(membership.get("workflow_id") or self.workflow_id),
            subject_ref=subject_ref,
            statework_id=statework_id,
            contract_version=str(contract_identity["contract_version"]))

    def workflow_contract_identity(self, statework_id: str,
                                   contract_hash: str) -> Dict[str, Any]:
        return self.workflow_authority.workflow_contract_identity(
            statework_id, contract_hash)

    def inspect_workflow(self, *, statework_id: str, subject_ref: str,
                         contract_hash: str) -> Any:
        identity = self._workflow_identity(
            statework_id=statework_id, subject_ref=subject_ref,
            contract_hash=contract_hash)
        return self.workflow_authority.inspect_workflow(
            identity, contract_hash=contract_hash)

    def resolve_legacy_step(self, *, statework_id: str, subject_ref: str,
                            contract_hash: str, to_state: str,
                            trigger: Optional[str]) -> str:
        identity = self._workflow_identity(
            statework_id=statework_id, subject_ref=subject_ref,
            contract_hash=contract_hash)
        return self.workflow_authority.resolve_legacy_step(
            identity, contract_hash=contract_hash, to_state=to_state,
            trigger=trigger)

    def apply_workflow_step(self, *, statework_id: str, subject_ref: str,
                            contract_hash: str, step_id: str,
                            expected_revision: int,
                            evidence_records: Optional[list[Mapping[str, Any]]] = None) -> Any:
        identity = self._workflow_identity(
            statework_id=statework_id, subject_ref=subject_ref,
            contract_hash=contract_hash)
        scoped_refs: list[str] = []
        for record in evidence_records or ():
            copied = dict(record)
            original_ref = str(copied.get("ref") or "")
            if not original_ref:
                raise ValueError("CSW evidence record requires a ref")
            scoped_ref = "evidence:" + hashlib.sha256(
                (f"{identity.namespace_id}|{identity.application_id}|"
                 f"{identity.application_instance_id}|{identity.workflow_id}|"
                 f"{statework_id}|{subject_ref}|{original_ref}").encode("utf-8")
            ).hexdigest()
            copied.update({"ref": scoped_ref, "origin_ref": original_ref,
                           "namespace_id": identity.namespace_id,
                           "application_id": identity.application_id,
                           "application_instance_id": identity.application_instance_id,
                           "workflow_id": identity.workflow_id})
            self.evidence_store.create(copied)
            scoped_refs.append(scoped_ref)
        if scoped_refs:
            self.evidence_store.save(self.evidence_path)
        return self.workflow_authority.apply_step(
            identity, contract_hash=contract_hash, step_id=step_id,
            evidence_refs=scoped_refs, expected_revision=expected_revision)

    def _identity(self, *, statework_id: str, subject_ref: str, contract: Mapping[str, Any]) -> Dict[str, Any]:
        return {"namespace_id": self.namespace_id, "application_id": self.application_id,
                "application_instance_id": self.application_instance_id,
                "workflow_id": self.workflow_id,
                "subject_ref": subject_ref, "statework_id": statework_id,
                "contract_version": str(contract.get("version") or "1.0.0")}

    def inspect(self, *, statework_id: str, subject_ref: str, contract_hash: str) -> Dict[str, Any]:
        snapshot = self.inspect_workflow(statework_id=statework_id,
                                         subject_ref=subject_ref,
                                         contract_hash=contract_hash)
        return {"state": snapshot.current_state, "current_state": snapshot.current_state,
                "revision": snapshot.revision, "updated_at": None,
                "engine_kind": snapshot.engine_kind,
                "completed": snapshot.completed,
                "workflow_data": dict(snapshot.data)}

    def commit(self, *, statework_id: str, subject_ref: str, contract_hash: str,
               expected_revision: int, output_state: str, evidence_refs: list[str], trigger: str,
               evidence_records: Optional[list[Mapping[str, Any]]] = None) -> Dict[str, Any]:
        snapshot = self.inspect_workflow(statework_id=statework_id,
                                         subject_ref=subject_ref,
                                         contract_hash=contract_hash)
        step_id = self.resolve_legacy_step(
            statework_id=statework_id, subject_ref=subject_ref,
            contract_hash=contract_hash, to_state=output_state, trigger=trigger)
        decision = self.apply_workflow_step(
            statework_id=statework_id, subject_ref=subject_ref,
            contract_hash=contract_hash, step_id=step_id,
            expected_revision=expected_revision, evidence_records=evidence_records)
        if not decision.allowed:
            raise ValueError(f"CSW authority blocked workflow step: {decision.reason}")
        return {"state": decision.current_state, "current_state": decision.current_state,
                "revision": decision.revision, "updated_at": None,
                "engine_kind": decision.engine_kind,
                "completed": decision.completed,
                "workflow_data": dict(decision.state_data),
                "transition": decision.to_dict()}
