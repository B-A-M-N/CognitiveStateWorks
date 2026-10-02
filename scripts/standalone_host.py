"""CSW-only host interface for standalone workflow execution."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

if __package__:
    from .errors import TransitionError
    from .evidence import EvidenceStore
    from .resources import (_aware_datetime, _load_yaml,
                            load_evidence_kind_registry)
    from .state_store import PacketStore, SubjectStateStore
    from .transition_engine import TransitionDecision
    from .workflow_controller import StandaloneStateWorkController
else:
    from errors import TransitionError
    from evidence import EvidenceStore
    from resources import (_aware_datetime, _load_yaml,
                           load_evidence_kind_registry)
    from state_store import PacketStore, SubjectStateStore
    from transition_engine import TransitionDecision
    from workflow_controller import StandaloneStateWorkController

class StandaloneHostInterface:
    """Small host facade for enforcing installations."""
    def __init__(self, *, root: Path, state_path: Optional[Path] = None,
                 evidence_path: Optional[Path] = None) -> None:
        self.root = Path(root)
        self.evidence_path = Path(evidence_path) if evidence_path else self.root / "state" / "evidence.json"
        self.state_store = SubjectStateStore(Path(state_path) if state_path else self.root / "state" / "subjects.json")
        self.evidence_store = EvidenceStore()
        self.packet_store = PacketStore(
            packet_registry_path=self.root / "schemas" / "packet-registry.yaml",
            storage_path=self.root / "state" / "packets.json")
        self._controllers: Dict[str, StandaloneStateWorkController] = {}
        self._controller_contract_hashes: Dict[str, str] = {}
        self._load_evidence()

    def _load_evidence(self) -> None:
        if not self.evidence_path or not self.evidence_path.exists():
            return
        try:
            data = json.loads(self.evidence_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TransitionError("trusted evidence store is unreadable") from exc
        if not isinstance(data, list):
            raise TransitionError("trusted evidence store must contain a list")
        for record in data:
            self.evidence_store.put(record)

    def resolve_statework(self, statework_id: str) -> Dict[str, Any]:
        registry = _load_yaml(self.root / "registry.yaml")
        if statework_id not in set((registry or {}).get("stateworks", [])):
            raise TransitionError(f"unknown StateWork {statework_id!r}")
        base = self.root / statework_id
        return {"id": statework_id, "manifest": _load_yaml(base / "manifest.yaml"),
                "contract": _load_yaml(base / "transitions.yaml")}

    def start_or_resume(self, *, statework_id: str, identity: Mapping[str, Any]) -> Dict[str, Any]:
        if identity.get("statework_id") != statework_id:
            raise TransitionError("requested StateWork does not match the subject identity")
        statework = self.resolve_statework(statework_id)
        contract = statework["contract"]
        contract_hash = hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        key = SubjectStateStore.key(identity)
        controller = self._controllers.get(key)
        if controller is None or self._controller_contract_hashes.get(key) != contract_hash:
            registry = load_evidence_kind_registry(self.root / "schemas" / "evidence-kinds.yaml")
            controller = StandaloneStateWorkController(contract=contract, identity=identity,
                                                       state_store=self.state_store,
                                                       evidence_store=self.evidence_store,
                                                       evidence_registry=registry)
            self._controllers[key] = controller
            self._controller_contract_hashes[key] = contract_hash
        return controller.inspect()

    def submit_attested_observation(self, record: Mapping[str, Any]) -> str:
        if not isinstance(record, Mapping):
            raise TransitionError("observation must be a mapping")
        candidate = dict(record)
        kind = candidate.get("kind")
        registry = load_evidence_kind_registry(self.root / "schemas" / "evidence-kinds.yaml")
        spec = (registry.get("kinds") or {}).get(kind)
        if spec:
            if not spec.get("mintable_by_host"):
                raise TransitionError(
                    f"evidence kind {kind!r} requires its registered specialized issuer")
            if len(spec.get("allowed_issuers") or []) != 1:
                raise TransitionError(f"host-minted evidence kind {kind!r} has ambiguous issuers")
            metadata = {
                "issuer": spec["allowed_issuers"][0],
                "validator": spec["validator"],
                "schema": spec["schema"],
            }
            for key, value in metadata.items():
                if key in candidate and candidate[key] != value:
                    raise TransitionError(f"caller cannot declare trusted evidence field {key!r}")
                candidate[key] = value
            if not isinstance(candidate.get("subject_ref"), str) or not candidate["subject_ref"]:
                raise TransitionError("registered evidence requires subject_ref")
            _aware_datetime(candidate.get("observed_at"))
            digest = candidate.get("content_digest")
            if not isinstance(digest, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
                raise TransitionError(
                    "registered evidence requires a SHA-256 content_digest from the host observation")
        ref = self.evidence_store.create(candidate)
        self.evidence_store.save(self.evidence_path)
        return ref

    def publish_packet(self, packet: Mapping[str, Any], *, storage_path: Optional[Path] = None) -> str:
        """Publish a validated handoff packet through CSW's typed store."""
        if not isinstance(packet, Mapping):
            raise TransitionError("handoff packet must be a mapping")
        if storage_path is not None:
            store = PacketStore(
                packet_registry_path=self.root / "schemas" / "packet-registry.yaml",
                storage_path=storage_path)
        else:
            store = self.packet_store
        return store.put(dict(packet))

    def recover_from_invalidation(self, *, evidence_ref: str, identity: Mapping[str, Any],
                                 statework_id: str) -> Dict[str, Any]:
        """Record trusted invalidation and return the authoritative reinspection state."""
        self.evidence_store.invalidate(evidence_ref)
        self.evidence_store.save(self.evidence_path)
        return self.start_or_resume(statework_id=statework_id, identity=identity)

    def request_transition(self, *, statework_id: str, identity: Mapping[str, Any],
                           to_state: str, trigger: str, evidence_refs: Iterable[str],
                           expected_revision: int) -> TransitionDecision:
        self.start_or_resume(statework_id=statework_id, identity=identity)
        controller = self._controllers[SubjectStateStore.key(identity)]
        return controller.request_transition(to_state=to_state, trigger=trigger,
                                              evidence_refs=evidence_refs,
                                              expected_revision=expected_revision)
