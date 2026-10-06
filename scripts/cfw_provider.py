"""Optional CFW provider entry point implemented by CognitiveStateWork."""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

import yaml


class CognitiveStateWorkProviderError(ValueError):
    """A StateWork checkout or compiled registry violates its runtime contract."""


class CognitiveStateWorkProvider:
    """Bridge from a CSW checkout's compiled registry and validated primitives."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self._control: Any = None
        self._compiled: Optional[Any] = None

    @staticmethod
    def default_root() -> Path:
        """Return this installed/source distribution's registry root."""
        module_root = Path(__file__).resolve().parent
        source_root = module_root.parent
        if (source_root / "registry.yaml").is_file():
            return source_root
        return module_root

    def _control_plane(self) -> Any:
        if self._control is not None:
            return self._control
        try:
            module = importlib.import_module("cognitive_statework.control_plane")
        except Exception as exc:
            raise CognitiveStateWorkProviderError(
                f"CognitiveStateWork control plane is unavailable: {exc}") from exc
        self._control = module
        return self._control

    def create_state_authority(self, **options: Any) -> Any:
        """Build the CSW-owned adapter for CFW's neutral StateAuthority port."""
        from .cfw_authority import CFWAuthorityAdapter
        return CFWAuthorityAdapter(
            self.root, control_plane_module=self._control_plane(), **options)

    def _compiled_registry(self) -> Any:
        if self._compiled is None:
            try:
                opener = getattr(self._control_plane(), "open_compiled_registry", None)
                if not callable(opener):
                    raise CognitiveStateWorkProviderError(
                        "CognitiveStateWork lacks the canonical compiled-registry flow API")
                data = opener(self.root)
            except Exception as exc:
                if isinstance(exc, CognitiveStateWorkProviderError):
                    raise
                raise CognitiveStateWorkProviderError(
                    f"compiled StateWork registry is invalid: {exc}") from exc
            if not isinstance(data, Mapping):
                raise CognitiveStateWorkProviderError("compiled StateWork registry is invalid")
            # Keep the canonical CompiledRegistry service object intact.
            # Converting it to dict discards flow_contract()/flow_metadata(),
            # forcing the adapter to reimplement CSW validation details.
            self._compiled = data
        return self._compiled

    def _workflow_planner(self) -> Any:
        from .workflow_planner import WorkflowPlanner

        compiled = self._compiled_registry()
        return WorkflowPlanner(
            compiled, self.root,
            packet_store_factory=lambda packets: self._control_plane().PacketStore(
                packets, packet_registry_data=compiled.get("packet_registry") or {},
                packet_schemas=compiled.get("packet_schemas") or {}))

    def eligible_routes(self, *, runtime_identity: Mapping[str, Any],
                        task_context: Mapping[str, Any]) -> Dict[str, Any]:
        """Return workflow choices authorized by the compiled CSW registry."""
        return self._workflow_planner().eligible_routes(runtime_identity, task_context)

    def resolve_workflows(self, *, runtime_identity: Mapping[str, Any],
                          task_context: Mapping[str, Any],
                          routing_adjustments: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        """Resolve the final legal workflow plan after bounded host preferences."""
        return self._workflow_planner().resolve_workflows(
            runtime_identity, task_context, routing_adjustments)

    def rank_legal_routes(self, *, runtime_identity: Mapping[str, Any],
                          task_context: Mapping[str, Any], statework_id: str,
                          candidate_routes: Iterable[str],
                          expected_workflow_revision: int,
                          state_authority: Any) -> Dict[str, Any]:
        """Rank resolved child routes under the bound CSW workflow authority."""
        return self._workflow_planner().rank_legal_routes(
            runtime_identity, task_context, statework_id,
            candidate_routes, expected_workflow_revision, state_authority)

    def load_stateworks(self) -> list[dict[str, Any]]:
        compiled = self._compiled_registry()
        out = []
        for entry in compiled.get("stateworks") or ():
            data = dict(entry.get("manifest") or {})
            owner = Path(str(entry.get("bundle_root") or ""))
            if not owner.is_dir():
                raise CognitiveStateWorkProviderError(
                    f"compiled StateWork {entry.get('id')!r} source root is missing")
            data["_manifest_path"] = owner / "manifest.yaml"
            data["_bundle_root"] = str(owner)
            data["_bundle_hash"] = entry.get("bundle_hash")
            data["_compiled_engine"] = dict(entry.get("engine") or {})
            data["_runtime_capsule"] = str(entry.get("runtime_capsule") or "")
            data["_runtime_capsule_hash"] = str(entry.get("runtime_capsule_hash") or "")
            out.append(data)
        for item in out:
            self.validate_flow_contracts(str(item.get("id") or ""),
                                          owner_root=Path(item["_bundle_root"]))
        return out

    def packet_registry(self) -> Dict[str, Any]:
        data = self._compiled_registry().get("packet_registry") or {}
        return dict(data) if isinstance(data, Mapping) else {"packets": {}}

    def packet_store(self, packets: Optional[Iterable[Dict[str, Any]]], *,
                     storage_path: Optional[Path] = None) -> Any:
        compiled = self._compiled_registry()
        return self._control_plane().PacketStore(
            packets, packet_registry_data=compiled.get("packet_registry") or {},
            packet_schemas=compiled.get("packet_schemas") or {},
            storage_path=storage_path)

    def packet_metadata(self, packet_type: str) -> Dict[str, Any]:
        registry = self.packet_registry()
        packets = registry.get("packets") if isinstance(registry, Mapping) else None
        value = packets.get(str(packet_type)) if isinstance(packets, Mapping) else None
        return dict(value) if isinstance(value, Mapping) else {}

    def evidence_kind_registry(self) -> Dict[str, Any]:
        return self._control_plane().load_evidence_kind_registry(
            self.root / "schemas" / "evidence-kinds.yaml")

    def validate_repository_truth(self, packet: Mapping[str, Any],
                                  observation_context: Mapping[str, Any]) -> bool:
        return bool(self.packet_store(None).validate_current(
            dict(packet), observation_context=dict(observation_context)))

    def bundle_root(self, statework: Any) -> Path:
        if isinstance(statework, Mapping) and statework.get("_bundle_root"):
            return Path(str(statework["_bundle_root"]))
        statework_id = (str(statework.get("id") or "") if isinstance(statework, Mapping)
                        else str(statework))
        entry = next((item for item in self._compiled_registry().get("stateworks", ())
                      if item.get("id") == statework_id), None)
        if entry is None:
            raise CognitiveStateWorkProviderError(
                f"compiled StateWork {statework_id!r} is unavailable")
        return Path(str(entry["bundle_root"]))

    def validate_flow_contracts(self, statework_id: str, *,
                                owner_root: Optional[Path] = None) -> None:
        compiled = self._compiled_registry()
        expected_root = self.bundle_root(statework_id).resolve()
        if owner_root is not None and Path(owner_root).resolve() != expected_root:
            raise CognitiveStateWorkProviderError(
                f"StateWork {statework_id!r} flow root differs from the compiled registry")
        try:
            compiled.flow_contract(statework_id)
        except Exception as exc:
            raise CognitiveStateWorkProviderError(
                f"StateWork {statework_id!r} flow contract is invalid: {exc}") from exc

    def flow_metadata(self, statework: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
        statework_id = str(statework.get("id") or "")
        self.validate_flow_contracts(statework_id, owner_root=self.bundle_root(statework))
        return self._compiled_registry().flow_metadata(statework_id)

    def flow_selector(self) -> Any:
        return self._control_plane().FlowSelector

    def registry_document(self) -> Dict[str, Any]:
        try:
            data = yaml.safe_load((self.root / "registry.yaml").read_text(encoding="utf-8"))
        except Exception as exc:
            raise CognitiveStateWorkProviderError(f"StateWork registry is invalid: {exc}") from exc
        if not isinstance(data, Mapping):
            raise CognitiveStateWorkProviderError("StateWork registry is invalid")
        return dict(data)
