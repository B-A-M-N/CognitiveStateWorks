"""Compiled StateWork bundle registry and source-integrity loader."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Optional

import jsonschema
import yaml
try:
    from .control_plane import (EVIDENCE_VALIDATORS, FRESHNESS_VALIDATORS,
                                ROOT, TransitionEngine,
                                TransitionError, _load_yaml, render_runtime_capsule,
                                load_evidence_kind_registry, load_packet_registry)
    from .bundles import BundleFiles
    from .contracts import load_fragment, validate_flow_file, validate_packet_schema
    from .workflow_engines import (EngineRegistry, MilestoneWorkflowEngine,
                                   StateMachineWorkflowEngine)
except ImportError:
    from control_plane import (EVIDENCE_VALIDATORS, FRESHNESS_VALIDATORS,
                               ROOT, TransitionEngine,
                               TransitionError, _load_yaml, render_runtime_capsule,
                               load_evidence_kind_registry, load_packet_registry)
    from bundles import BundleFiles
    from contracts import load_fragment, validate_flow_file, validate_packet_schema
    from workflow_engines import (EngineRegistry, MilestoneWorkflowEngine,
                                  StateMachineWorkflowEngine)


class RegistryCompiler:
    """Compile trusted bundle roots into one immutable, content-addressed registry."""
    VERSION = "2.0.0"
    BUILTIN_ENGINE_SOURCE_MANIFEST = {
        "state_machine": ("workflow_engines.py", "transition_engine.py", "evidence.py"),
        "milestone": ("workflow_engines.py",),
        "flow_selector": ("flow_selectors.py",),
    }

    def __init__(self, root: Optional[Path] = None, *,
                 engine_registry: Optional[EngineRegistry] = None):
        self.root = Path(root or ROOT).resolve()
        self.engine_registry = engine_registry or EngineRegistry()

    @staticmethod
    def _digest(value: Any) -> str:
        return hashlib.sha256(json.dumps(
            value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

    @staticmethod
    def _source_manifest_hash(source_files: tuple[str, ...]) -> str:
        digest = hashlib.sha256()
        root = Path(__file__).parent
        for source_name in source_files:
            if (not isinstance(source_name, str) or not source_name
                    or Path(source_name).is_absolute()
                    or ".." in Path(source_name).parts):
                raise ValueError("CSW source hash manifest contains an unsafe path")
            source = root / source_name
            if source.is_symlink() or not source.is_file():
                raise TransitionError(
                    f"CSW implementation source is missing or linked: {source_name}")
            digest.update(source_name.replace("\\", "/").encode("utf-8"))
            digest.update(b"\0")
            digest.update(source.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    @classmethod
    def _builtin_engine_hashes(cls) -> dict[str, str]:
        return {engine: cls._source_manifest_hash(files)
                for engine, files in cls.BUILTIN_ENGINE_SOURCE_MANIFEST.items()}

    @classmethod
    def _registry_compiler_hash(cls) -> str:
        return cls._source_manifest_hash(("registry.py", "compile-registry.py"))

    @classmethod
    def _compatibility_api_hash(cls) -> str:
        return cls._source_manifest_hash(("control_plane.py",))

    @staticmethod
    def _relative_file(bundle_root: Path, name: str) -> Path:
        return BundleFiles.relative_file(bundle_root, name)

    def _bundle_files(self, bundle_root: Path) -> dict[str, str]:
        return BundleFiles.hashes(bundle_root)

    def _load_fragment(self, bundle_root: Path, relative: Optional[str], *,
                       fragment: str) -> dict[str, Any]:
        return load_fragment(bundle_root, relative, fragment=fragment)

    def compile(self, *, write: bool = False) -> dict[str, Any]:
        registry_path = self.root / "registry.yaml"
        registry = _load_yaml(registry_path) or {}
        if str(registry.get("version")) != self.VERSION:
            raise TransitionError("registry.yaml must declare registry bundle version 2.0.0")
        base_ids = list(registry.get("stateworks") or ())
        if len(base_ids) != len(set(base_ids)):
            raise TransitionError("registry.yaml contains duplicate StateWork IDs")
        roots: list[tuple[str, Path, Optional[list[str]]]] = [(".", self.root, base_ids)]
        for index, raw in enumerate(registry.get("extension_roots") or ()):
            if not isinstance(raw, str) or not raw:
                raise TransitionError("extension_roots must contain trusted root paths")
            target = Path(raw).expanduser()
            target = (self.root / target).resolve() if not target.is_absolute() else target.resolve()
            if not target.is_dir() or target.is_symlink():
                raise TransitionError(f"trusted extension root is unavailable or linked: {raw}")
            roots.append((f"extension:{index}", target, None))

        global_packets = load_packet_registry(self.root / "schemas" / "packet-registry.yaml")
        global_evidence = load_evidence_kind_registry(
            self.root / "schemas" / "evidence-kinds.yaml")
        packet_rows: dict[str, dict[str, Any]] = dict(global_packets.get("packets") or {})
        packet_schema_docs: dict[str, dict[str, Any]] = {}
        for packet_id, meta in packet_rows.items():
            schema_path = self.root / "schemas" / str(meta.get("schema") or "")
            if schema_path.is_file():
                packet_schema_docs[packet_id] = json.loads(schema_path.read_text(encoding="utf-8"))
        evidence_rows: dict[str, dict[str, Any]] = dict(global_evidence.get("kinds") or {})
        compiled: list[dict[str, Any]] = []
        source_by_id: dict[str, tuple[str, Path]] = {}

        for root_ref, source_root, explicit_ids in roots:
            candidates = ([source_root / sid for sid in explicit_ids]
                          if explicit_ids is not None else sorted(
                              path.parent for path in source_root.glob("*/manifest.yaml")))
            for bundle_root in candidates:
                manifest_path = bundle_root / "manifest.yaml"
                if not manifest_path.is_file() or manifest_path.is_symlink():
                    raise TransitionError(f"bundle {bundle_root} is missing a regular manifest.yaml")
                manifest = _load_yaml(manifest_path) or {}
                sid = str(manifest.get("id") or "")
                if not sid or sid != bundle_root.name or sid in source_by_id:
                    raise TransitionError(f"StateWork identifier collision or path mismatch: {sid!r}")
                schema_path = self.root / "schemas" / "statework-manifest.schema.json"
                jsonschema.validate(instance=manifest,
                                    schema=json.loads(schema_path.read_text(encoding="utf-8")))
                if manifest.get("bundle_schema_version") != 2:
                    raise TransitionError(f"StateWork {sid!r} must use bundle schema version 2")
                flow_policy = manifest.get("flow_selection") or {}
                flow_schema_path = self.root / "schemas" / "statework-flow.schema.json"
                flow_schema = json.loads(flow_schema_path.read_text(encoding="utf-8"))
                flow_paths = sorted(bundle_root.glob("flows/*/flow.md"))
                fallbacks = []
                for flow_path in flow_paths:
                    try:
                        flow_meta = validate_flow_file(
                            flow_path, flow_schema=flow_schema,
                            engine_kind=str((manifest.get("engine") or {}).get("kind") or ""))
                    except (ValueError, jsonschema.ValidationError, yaml.YAMLError) as exc:
                        raise TransitionError(
                            f"StateWork {sid!r} flow {flow_path.parent.name!r} is invalid: {exc}") from exc
                    if flow_meta.get("fallback") is True:
                        fallbacks.append(flow_path.parent.name)
                fallback_policy = str(flow_policy.get("fallback"))
                if ((fallback_policy == "required" and len(fallbacks) != 1)
                        or (fallback_policy == "optional" and len(fallbacks) > 1)
                        or (fallback_policy == "forbidden" and fallbacks)):
                    raise TransitionError(
                        f"StateWork {sid!r} fallback policy {fallback_policy!r} "
                        f"does not match declared fallback flows {fallbacks}")
                files = self._bundle_files(bundle_root)
                if "manifest.yaml" not in files:
                    raise TransitionError(f"StateWork {sid!r} manifest is not part of its bundle")
                engine_decl = manifest.get("engine") or {}
                kind = str(engine_decl.get("kind") or "")
                contract_relative = str(engine_decl.get("contract") or "")
                contract_path = self._relative_file(bundle_root, contract_relative)
                workflow_contract = _load_yaml(contract_path) or {}
                contract_schema_name = {
                    "state_machine": "transition-contract.schema.json",
                    "milestone": "milestone-contract.schema.json",
                }.get(kind)
                if contract_schema_name is not None:
                    contract_schema_path = self.root / "schemas" / contract_schema_name
                    if (contract_schema_path.is_symlink()
                            or not contract_schema_path.is_file()):
                        raise TransitionError(
                            f"workflow contract schema is unavailable: {contract_schema_name}")
                    jsonschema.validate(
                        instance=workflow_contract,
                        schema=json.loads(contract_schema_path.read_text(encoding="utf-8")))
                contracts = manifest.get("contracts") or {}
                local_packets = self._load_fragment(
                    bundle_root, contracts.get("packets"), fragment="packets")
                local_evidence = self._load_fragment(
                    bundle_root, contracts.get("evidence"), fragment="kinds")
                for packet_id, row in local_packets.items():
                    if not isinstance(row, Mapping):
                        raise TransitionError(f"packet fragment {packet_id!r} is malformed")
                    schema_relative = str(row.get("schema") or "")
                    _local_schema_path, schema_doc = validate_packet_schema(
                        bundle_root, {**dict(row), "schema": schema_relative})
                    existing = packet_rows.get(str(packet_id))
                    if existing is not None:
                        previous_schema = packet_schema_docs.get(str(packet_id))
                        if ({key: value for key, value in existing.items() if key != "schema"}
                                != {key: value for key, value in row.items() if key != "schema"}
                                or previous_schema is not None and previous_schema != schema_doc):
                            raise TransitionError(f"packet contract collision for {packet_id!r}")
                    packet_rows[str(packet_id)] = dict(row)
                    packet_schema_docs[str(packet_id)] = schema_doc
                for kind_id, row in local_evidence.items():
                    if not isinstance(row, Mapping):
                        raise TransitionError(f"evidence declaration {kind_id!r} is malformed")
                    existing = evidence_rows.get(str(kind_id))
                    if existing is not None and dict(existing) != dict(row):
                        raise TransitionError(f"evidence kind collision for {kind_id!r}")
                    evidence_rows[str(kind_id)] = dict(row)

                if kind == "state_machine":
                    evidence_registry = {"kinds": evidence_rows}
                    engine_impl: Any = StateMachineWorkflowEngine(TransitionEngine(
                        dict(workflow_contract), evidence_registry=evidence_registry,
                        require_registered=True))
                elif kind == "milestone":
                    engine_impl = MilestoneWorkflowEngine()
                else:
                    engine_impl = self.engine_registry.get(kind)
                engine_impl.validate_contract(workflow_contract)
                contract_digest = self._digest(workflow_contract)

                ref = (bundle_root.relative_to(source_root).as_posix()
                       if bundle_root != source_root else ".")
                try:
                    source_root_ref = source_root.relative_to(self.root).as_posix()
                except ValueError:
                    source_root_ref = str(source_root)
                if source_root == self.root:
                    source_root_ref = "."
                files_digest = self._digest(files)
                guidance_path = bundle_root / "guidance.md"
                guidance = (guidance_path.read_text(encoding="utf-8")
                            if guidance_path.is_file() and not guidance_path.is_symlink()
                            else "")
                runtime_capsule = render_runtime_capsule(
                    manifest, engine_kind=kind,
                    contract_version=str(engine_decl.get("contract_version") or ""),
                    flows=(path.parent.name for path in flow_paths),
                    guidance=guidance)
                source_by_id[sid] = (root_ref, source_root)
                compiled.append({
                    "id": sid, "root_ref": root_ref,
                    "source_root": source_root_ref,
                    "bundle_ref": ref, "bundle_hash": files_digest,
                    "file_hashes": files, "manifest": dict(manifest),
                    "engine": {"kind": kind,
                               "contract_version": str(engine_decl.get("contract_version") or ""),
                               "contract_path": contract_relative,
                               "contract_hash": contract_digest,
                               "contract": dict(workflow_contract)},
                    "runtime_capsule": runtime_capsule,
                    "runtime_capsule_hash": hashlib.sha256(
                        runtime_capsule.encode("utf-8")).hexdigest(),
                    "contracts": {"packets": list(local_packets),
                                  "evidence": list(local_evidence)}})

        by_id = {item["id"]: item for item in compiled}
        for item in compiled:
            composition = item["manifest"].get("composition") or {}
            missing = set(composition.get("requires") or ()) - set(by_id)
            if missing:
                raise TransitionError(f"StateWork {item['id']!r} requires missing bundles: {sorted(missing)}")
            unknown_conflicts = set(composition.get("conflicts") or ()) - set(by_id)
            if unknown_conflicts:
                raise TransitionError(f"StateWork {item['id']!r} names missing conflicts: {sorted(unknown_conflicts)}")
        for packet_id, meta in packet_rows.items():
            producer = str(meta.get("producer") or "")
            if producer and producer not in by_id:
                raise TransitionError(
                    f"packet {packet_id!r} names unavailable producer {producer!r}")

        body = {"registry_version": self.VERSION,
                "registry_config_hash": hashlib.sha256(registry_path.read_bytes()).hexdigest(),
                "stateworks": compiled,
                "packet_registry": {"version": "2.0.0", "packets": packet_rows},
                "packet_schemas": packet_schema_docs,
                "evidence_registry": {"version": str(global_evidence.get("version") or "1.0.0"),
                                      "kinds": evidence_rows},
                "evidence_validator_hashes": dict(EVIDENCE_VALIDATORS.identities),
                "freshness_validator_hashes": dict(FRESHNESS_VALIDATORS.identities),
                "builtin_engine_hashes": self._builtin_engine_hashes(),
                "registry_compiler_hash": self._registry_compiler_hash(),
                "compatibility_api_hash": self._compatibility_api_hash(),
                "workflow_engine_hashes": dict(self.engine_registry.identities)}
        result = {**body, "registry_hash": self._digest(body)}
        if write:
            path = self.root / "compiled-registry.json"
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                                 encoding="utf-8")
            os.replace(temporary, path)
        return result


class CompiledRegistry(Mapping[str, Any]):
    """Verified compiled registry with canonical StateWork flow services."""

    def __init__(self, data: Mapping[str, Any], *, root: Path):
        if not isinstance(data, Mapping):
            raise TypeError("compiled registry data must be a mapping")
        self._data = dict(data)
        self.root = Path(root).resolve()

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def _entry(self, statework_id: str) -> Mapping[str, Any]:
        entry = next((item for item in self._data.get("stateworks", ())
                      if isinstance(item, Mapping) and item.get("id") == statework_id), None)
        if entry is None:
            raise TransitionError(f"compiled StateWork {statework_id!r} is unavailable")
        return entry

    def flow_metadata(self, statework_id: str) -> dict[str, dict[str, Any]]:
        """Return validated frontmatter for every declared flow in a StateWork."""
        entry = self._entry(str(statework_id))
        bundle_root = Path(str(entry.get("bundle_root") or ""))
        if not bundle_root.is_dir():
            raise TransitionError(f"compiled StateWork {statework_id!r} source root is missing")
        schema_path = self.root / "schemas" / "statework-flow.schema.json"
        flow_schema = json.loads(schema_path.read_text(encoding="utf-8"))
        engine_kind = str((entry.get("manifest") or {}).get("engine", {}).get("kind") or "")
        flows_dir = bundle_root / "flows"
        result: dict[str, dict[str, Any]] = {}
        for path in sorted(flows_dir.glob("*/flow.md")) if flows_dir.is_dir() else ():
            result[path.parent.name] = validate_flow_file(
                path, flow_schema=flow_schema, engine_kind=engine_kind)
        return result

    def flow_contract(self, statework_id: str) -> dict[str, Any]:
        """Return and validate a StateWork's flow-selection policy and flows."""
        entry = self._entry(str(statework_id))
        manifest = entry.get("manifest") or {}
        policy = manifest.get("flow_selection") or {}
        if not isinstance(policy, Mapping):
            raise TransitionError(f"StateWork {statework_id!r} flow policy is malformed")
        flows = self.flow_metadata(str(statework_id))
        fallbacks = sorted(name for name, metadata in flows.items()
                           if metadata.get("fallback") is True)
        fallback_policy = str(policy.get("fallback") or "")
        if ((fallback_policy == "required" and len(fallbacks) != 1)
                or (fallback_policy == "optional" and len(fallbacks) > 1)
                or (fallback_policy == "forbidden" and fallbacks)):
            raise TransitionError(
                f"StateWork {statework_id!r} fallback policy {fallback_policy!r} "
                f"does not match declared flows {fallbacks}")
        return {"statework_id": str(statework_id), "policy": dict(policy),
                "flows": flows}


def load_compiled_registry(root: Optional[Path] = None, *,
                           verify_bundles: bool = True) -> dict[str, Any]:
    """Load the immutable compile artifact and verify its complete source hashes."""
    root = Path(root or ROOT).resolve()
    path = root / "compiled-registry.json"
    if not path.is_file() or path.is_symlink():
        raise TransitionError("compiled-registry.json is required; run compile-registry.py")
    result = json.loads(path.read_text(encoding="utf-8"))
    body = {key: value for key, value in result.items() if key != "registry_hash"}
    if result.get("registry_hash") != RegistryCompiler._digest(body):
        raise TransitionError("compiled registry content hash is invalid")
    if result.get("registry_version") != RegistryCompiler.VERSION:
        raise TransitionError("compiled registry version is unsupported")
    if result.get("freshness_validator_hashes") != dict(FRESHNESS_VALIDATORS.identities):
        raise TransitionError("compiled freshness-validator registry changed")
    if result.get("evidence_validator_hashes") != dict(EVIDENCE_VALIDATORS.identities):
        raise TransitionError("compiled evidence-validator registry changed")
    if result.get("builtin_engine_hashes") != RegistryCompiler._builtin_engine_hashes():
        raise TransitionError("compiled workflow engine implementation changed")
    if result.get("registry_compiler_hash") != RegistryCompiler._registry_compiler_hash():
        raise TransitionError("compiled CSW registry compiler implementation changed")
    if result.get("compatibility_api_hash") != RegistryCompiler._compatibility_api_hash():
        raise TransitionError("compiled CSW compatibility API changed")
    for item in result.get("stateworks") or ():
        capsule = str(item.get("runtime_capsule") or "")
        capsule_hash = hashlib.sha256(capsule.encode("utf-8")).hexdigest()
        if capsule_hash != item.get("runtime_capsule_hash"):
            raise TransitionError(
                f"compiled runtime capsule for {item.get('id')!r} has an invalid hash")
        source_root_ref = str(item.get("source_root") or ".")
        source_root = (root if source_root_ref == "." else
                       Path(source_root_ref) if Path(source_root_ref).is_absolute()
                       else root / source_root_ref)
        bundle_root = (source_root / str(item.get("bundle_ref") or ".")).resolve()
        if verify_bundles:
            actual: dict[str, str] = {}
            for rel, expected in dict(item.get("file_hashes") or {}).items():
                file_path = RegistryCompiler._relative_file(bundle_root, rel)
                actual[rel] = hashlib.sha256(file_path.read_bytes()).hexdigest()
                if actual[rel] != expected:
                    raise TransitionError(f"compiled StateWork {item.get('id')!r} changed: {rel}")
            if RegistryCompiler._digest(actual) != item.get("bundle_hash"):
                raise TransitionError(f"compiled StateWork {item.get('id')!r} bundle hash changed")
        item["bundle_root"] = str(bundle_root)
    return result


def open_compiled_registry(root: Optional[Path] = None, *,
                           verify_bundles: bool = True) -> CompiledRegistry:
    """Load the verified registry and expose its canonical flow services."""
    registry_root = Path(root or ROOT).resolve()
    return CompiledRegistry(
        load_compiled_registry(registry_root, verify_bundles=verify_bundles),
        root=registry_root)
