"""CSW-owned workflow eligibility, composition, and runtime planning."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

try:
    from .flow_selectors import FlowSelector
    from .composition_rules import composition_for, validate_selection
except ImportError:
    from flow_selectors import FlowSelector
    from composition_rules import composition_for, validate_selection


class WorkflowPlanError(ValueError):
    """A requested workflow plan is ambiguous, invalid, or not composable."""


class AmbiguousWorkflowMatch(WorkflowPlanError):
    """A domain matched multiple equally ranked StateWork roots."""

    def __init__(self, message: str, candidates: Iterable[str]):
        self.candidates = tuple(sorted(set(str(item) for item in candidates)))
        super().__init__(message)


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _tokens(value: str) -> set[str]:
    return set(_norm(value).split())


class WorkflowPlanner:
    """Build plans only from CSW's compiled registry and packet authority."""

    def __init__(self, compiled: Mapping[str, Any], root: Path, *,
                 packet_store_factory: Any):
        self.compiled = compiled
        self.root = Path(root).resolve()
        self.packet_store_factory = packet_store_factory
        self.entries = {
            str(item.get("id")): item
            for item in compiled.get("stateworks", ())
            if isinstance(item, Mapping) and item.get("id")
        }
        self.manifests = {
            statework_id: dict(entry.get("manifest") or {})
            for statework_id, entry in self.entries.items()
        }

    @staticmethod
    def _phase_tags(manifest: Mapping[str, Any]) -> set[str]:
        tags = set(str(value) for value in manifest.get("phase_tags") or ())
        if manifest.get("phase"):
            tags.add(str(manifest["phase"]))
        return tags

    def _matches_one(self, domain: str, phase: Optional[str]) -> tuple[Optional[str], list[str]]:
        normalized = _norm(domain)
        if not normalized:
            return None, []
        exact: list[str] = []
        scored: list[tuple[float, str]] = []
        for statework_id, manifest in self.manifests.items():
            if phase and phase not in self._phase_tags(manifest):
                continue
            labels = [_norm(statework_id), _norm(str(manifest.get("name") or ""))]
            triggers = [str(value) for value in manifest.get("triggers") or ()]
            match = manifest.get("match") or {}
            required = [str(value) for value in match.get("required_any") or ()]
            secondary = [str(value) for value in match.get("secondary") or ()]
            if required and not any(
                _norm(term) and (_norm(term) == normalized
                                 or f" {_norm(term)} " in f" {normalized} ")
                for term in required
            ):
                continue
            triggers.extend(secondary)
            if normalized in labels or any(normalized == _norm(item) for item in triggers):
                exact.append(statework_id)
                continue
            target = _tokens(domain)
            best = max((len(_tokens(term) & target) / len(_tokens(term))
                        for term in triggers if _tokens(term)), default=0.0)
            if best > 0:
                scored.append((best, statework_id))
        if exact:
            return (exact[0], []) if len(exact) == 1 else (None, sorted(exact))
        if not scored:
            return None, []
        top = max(score for score, _statework_id in scored)
        winners = sorted(statework_id for score, statework_id in scored
                         if abs(score - top) < 1e-9)
        return (winners[0], []) if len(winners) == 1 else (None, winners)

    def _roots(self, domains: Iterable[str], phase: Optional[str],
               requested_ids: Optional[Iterable[str]] = None) -> list[dict[str, Any]]:
        # Hosts send an empty tuple when they have no explicit root override.
        # Treat that the same as an omitted override so normal domain matching
        # still runs; only a non-empty list pins explicit roots.
        if requested_ids:
            ids = tuple(sorted(set(str(item) for item in requested_ids)))
            missing = set(ids) - set(self.manifests)
            if missing:
                raise WorkflowPlanError(
                    f"requested StateWork roots are unavailable: {sorted(missing)}")
            return [self.manifests[statework_id] for statework_id in ids]
        domain_list = [str(value) for value in domains]
        roots: dict[str, dict[str, Any]] = {}
        ambiguous: set[str] = set()
        for domain in domain_list:
            statework_id, conflicts = self._matches_one(str(domain), phase)
            ambiguous.update(conflicts)
            if statework_id:
                roots[statework_id] = self.manifests[statework_id]
        if ambiguous:
            raise AmbiguousWorkflowMatch(
                f"ambiguous StateWork match for domain(s) {domain_list}; "
                f"candidates: {sorted(ambiguous)}", ambiguous)
        return [roots[key] for key in sorted(roots)]

    @staticmethod
    def _consumed(manifest: Mapping[str, Any]) -> tuple[list[str], list[str]]:
        inputs = manifest.get("inputs")
        if isinstance(inputs, Mapping):
            return ([str(item) for item in inputs.get("required") or ()
                     if item != "task_context"],
                    [str(item) for item in inputs.get("optional") or ()
                     if item != "task_context"])
        return ([str(item) for item in manifest.get("consumes") or ()
                 if item != "task_context"], [])

    def _ordered_dependencies(self, roots: list[dict[str, Any]], context: Mapping[str, Any],
                              runtime_identity: Mapping[str, Any]) -> list[dict[str, Any]]:
        packet_registry = self.compiled.get("packet_registry") or {}
        producers = packet_registry.get("packets") or {}
        store = self.packet_store_factory(
            context.get("packet_records") or context.get("packets") or ())
        task_id = str(runtime_identity.get("task_id") or "task-unspecified")
        default_subject = runtime_identity.get("subject_ref")
        subject_refs = dict(context.get("statework_subject_refs") or {})
        observation_context = context.get("observation_context") or {}
        allow_missing = context.get("allow_missing_required") is True
        missing = context.get("missing_required")
        resolved: set[str] = set()
        visiting: set[str] = set()
        ordered: list[dict[str, Any]] = []
        satisfied_requirements: dict[str, set[str]] = {}

        def current_packet(statework_id: str, packet_type: str) -> Optional[dict[str, Any]]:
            subject = subject_refs.get(statework_id, default_subject)
            if not subject:
                return None
            return store.get_current(packet_type, task_id=task_id,
                                    subject_ref=str(subject),
                                    observation_context=observation_context)

        def visit(statework_id: str) -> None:
            if statework_id in resolved:
                return
            if statework_id in visiting:
                raise WorkflowPlanError(
                    f"StateWork dependency cycle detected at {statework_id!r}")
            manifest = self.manifests.get(statework_id)
            if manifest is None:
                raise WorkflowPlanError(f"required StateWork {statework_id!r} is unavailable")
            visiting.add(statework_id)
            required, _optional = self._consumed(manifest)
            composition = manifest.get("composition") or {}
            dependencies = set(str(item) for item in composition.get("requires") or ())
            for dependency in sorted(dependencies):
                packet_types = [packet for packet in required
                                if (producers.get(packet) or {}).get("producer") == dependency]
                if packet_types and all(current_packet(statework_id, packet)
                                        is not None for packet in packet_types):
                    satisfied_requirements.setdefault(statework_id, set()).add(dependency)
                    continue
                visit(dependency)
            for packet_type in required:
                metadata = producers.get(packet_type)
                if not metadata:
                    if allow_missing:
                        if isinstance(missing, list):
                            missing.append(packet_type)
                        continue
                    raise WorkflowPlanError(
                        f"required packet {packet_type!r} consumed by {statework_id!r} "
                        "is not registered")
                if current_packet(statework_id, packet_type) is not None:
                    continue
                producer = str(metadata.get("producer") or "")
                if producer not in self.manifests:
                    raise WorkflowPlanError(
                        f"packet {packet_type!r} has unavailable producer {producer!r}")
                visit(producer)
            visiting.remove(statework_id)
            resolved.add(statework_id)
            ordered.append(manifest)

        for root in roots:
            visit(str(root.get("id") or ""))

        active_ids = {str(item.get("id") or "") for item in ordered}
        try:
            validate_selection(self.manifests, active_ids,
                               satisfied_requirements=satisfied_requirements)
        except ValueError as exc:
            raise WorkflowPlanError(str(exc)) from exc
        return ordered

    def eligible_routes(self, runtime_identity: Mapping[str, Any],
                        task_context: Mapping[str, Any]) -> dict[str, Any]:
        roots = self._roots(
            task_context.get("domains") or (), task_context.get("phase"),
            task_context.get("requested_statework_ids"))
        planning_context = dict(task_context)
        planning_context["missing_required"] = None
        self._ordered_dependencies(roots, planning_context, runtime_identity)
        routes: list[dict[str, Any]] = []
        versions: dict[str, str] = {}
        flow_context = self._flow_context(task_context)
        for manifest in roots:
            statework_id = str(manifest.get("id") or "")
            entry = self.entries[statework_id]
            versions[statework_id] = str(manifest.get("version") or "0.0.0")
            routes.append({"route_type": "statework", "route": statework_id,
                           "statework_id": statework_id})
            flow_metadata = self._compiled_flow_metadata(statework_id)
            policy = dict(manifest.get("flow_selection") or {})
            selection = FlowSelector.select(flow_metadata, flow_context, policy)
            owner_root = Path(str(entry.get("bundle_root") or ""))
            for flow_name in selection.candidates:
                metadata = flow_metadata[flow_name]
                budget = {"low": 1, "medium": 2, "high": 3}.get(
                    manifest.get("context_budget", "medium"), 2)
                routes.append({"route_type": "flow", "route": flow_name,
                               "statework_id": statework_id,
                               "eligibility_conditions": {
                                   "when": metadata.get("when"),
                                   "fallback": metadata.get("fallback") is True},
                               "context_cost": {"specialist_budget": budget},
                               "dependencies": list(metadata.get("required_specialists") or ())})
                flow_root = owner_root / "flows" / flow_name
                for specialist in (list(metadata.get("required_specialists") or ())
                                   + list(metadata.get("optional_specialists") or ())):
                    candidate = (flow_root / str(specialist)).resolve()
                    if candidate.is_file():
                        try:
                            relative = candidate.relative_to(owner_root.resolve()).as_posix()
                        except ValueError:
                            continue
                        routes.append({"route_type": "specialist",
                                       "route": f"{statework_id}/{relative}",
                                       "statework_id": statework_id,
                                       "eligibility_conditions": {"flow": flow_name},
                                       "context_cost": {
                                           "required": specialist in
                                           (metadata.get("required_specialists") or ()),
                                           "specialist_budget": budget},
                                       "dependencies": [flow_name]})
        all_versions = {statework_id: str(manifest.get("version") or "0.0.0")
                        for statework_id, manifest in self.manifests.items()}
        return {"eligible_routes": routes, "workflow_versions": all_versions}

    @staticmethod
    def _flow_context(context: Mapping[str, Any]) -> dict[str, Any]:
        return {"operation": context.get("operation"),
                "trigger": context.get("trigger"),
                "task_shape": context.get("task_shape"),
                "phase": context.get("phase"),
                "current_state": context.get("current_state"),
                "domain_tags": list(context.get("domains") or ())}

    def _compiled_flow_metadata(self, statework_id: str) -> dict[str, dict[str, Any]]:
        from .registry import CompiledRegistry
        registry = self.compiled
        if not isinstance(registry, CompiledRegistry):
            raise WorkflowPlanError("CSW compiled registry service is unavailable")
        registry.flow_contract(statework_id)
        return registry.flow_metadata(statework_id)

    def resolve_workflows(self, runtime_identity: Mapping[str, Any],
                          task_context: Mapping[str, Any],
                          routing_adjustments: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        roots = self._roots(
            task_context.get("domains") or (), task_context.get("phase"),
            task_context.get("requested_statework_ids"))
        adjustments = list(routing_adjustments)
        root_ids = {str(item.get("id") or "") for item in roots}
        for item in adjustments:
            if (item.get("route_type") == "statework"
                    and str(item.get("route") or "") in root_ids
                    and item.get("disposition") == "suppress"):
                raise WorkflowPlanError("a required StateWork root cannot be suppressed")
        ordered = self._ordered_dependencies(roots, task_context, runtime_identity)
        requested_flows = dict(task_context.get("requested_flows") or {})
        suppressed_flows: dict[str, set[str]] = {}
        preferred_specialists: dict[str, set[str]] = {}
        suppressed_specialists: dict[str, set[str]] = {}
        for item in adjustments:
            owner = str(item.get("statework_id") or "")
            route = str(item.get("route") or "")
            disposition = item.get("disposition")
            kind = item.get("route_type")
            if kind == "flow":
                if disposition == "suppress":
                    suppressed_flows.setdefault(owner, set()).add(route)
                    if requested_flows.get(owner) == route:
                        requested_flows.pop(owner, None)
                elif disposition in {"prefer", "activate"} and route not in suppressed_flows.get(owner, set()):
                    requested_flows[owner] = route
            elif kind == "specialist":
                target = preferred_specialists if disposition == "prefer" else suppressed_specialists
                if disposition in {"prefer", "suppress"}:
                    target.setdefault(owner, set()).add(route)

        subject_refs = dict(task_context.get("statework_subject_refs") or {})
        default_subject = runtime_identity.get("subject_ref")
        active: list[dict[str, Any]] = []
        component_requirements: list[str] = []
        component_enhancements: list[str] = []
        capsules: dict[str, tuple[str, str]] = {}
        for manifest in ordered:
            statework_id = str(manifest.get("id") or "")
            entry = self.entries[statework_id]
            owner_root = Path(str(entry.get("bundle_root") or "")).resolve()
            item = self._pin_workflow(
                statework_id, manifest, entry, owner_root,
                self._flow_context(task_context),
                requested_flows.get(statework_id),
                suppressed_flows.get(statework_id, set()),
                preferred_specialists.get(statework_id, set()),
                suppressed_specialists.get(statework_id, set()))
            if item.get("flow_selection_status") == "inactive":
                continue
            item["subject_ref"] = subject_refs.get(statework_id, default_subject)
            self._collect_component_integrations(
                item.get("integrations"), component_requirements,
                component_enhancements)
            self._collect_component_integrations(
                item.get("flow_integrations"), component_requirements,
                component_enhancements)
            item.pop("integrations", None)
            item.pop("flow_integrations", None)
            metadata = item.get("flow_metadata")
            if isinstance(metadata, Mapping):
                metadata = dict(metadata)
                metadata.pop("integrations", None)
                item["flow_metadata"] = metadata
            active.append(item)
            capsules.update(item.pop("_capsules"))
        active_ids = {str(item.get("id") or "") for item in active}
        inactive_ids = {str(item.get("id") or "") for item in ordered} - active_ids
        producers = (self.compiled.get("packet_registry") or {}).get("packets") or {}
        for consumer in active:
            consumer_id = str(consumer.get("id") or "")
            required, _optional = self._consumed(consumer)
            dependencies = set(str(item) for item in
                               (consumer.get("composition") or {}).get("requires") or ())
            dependencies.update(str((producers.get(packet) or {}).get("producer") or "")
                                for packet in required)
            unavailable = dependencies & inactive_ids
            if unavailable:
                raise WorkflowPlanError(
                    f"active StateWork {consumer_id!r} depends on inactive "
                    f"StateWork(s) {sorted(unavailable)}")
        completion_claim_classes: dict[str, dict[str, dict[str, Any]]] = {}
        for item in active:
            statework_id = str(item.get("id") or "")
            flow_metadata = item.get("flow_metadata") or {}
            completion = (flow_metadata.get("completion") or {}
                          if isinstance(flow_metadata, Mapping) else {})
            claim_classes = completion.get("claim_classes") or {}
            if not isinstance(claim_classes, Mapping):
                raise WorkflowPlanError(
                    f"StateWork {statework_id!r} has a malformed completion contract")
            normalized: dict[str, dict[str, Any]] = {}
            for claim_class, requirement in claim_classes.items():
                evidence_kinds = (requirement.get("evidence_kinds")
                                  if isinstance(requirement, Mapping) else None)
                minimum_state = (requirement.get("minimum_state")
                                 if isinstance(requirement, Mapping) else None)
                if (not isinstance(claim_class, str) or not claim_class
                        or not isinstance(minimum_state, str) or not minimum_state
                        or not isinstance(evidence_kinds, (list, tuple))
                        or not evidence_kinds
                        or any(not isinstance(kind, str) or not kind
                               for kind in evidence_kinds)
                        or len(evidence_kinds) != len(set(evidence_kinds))):
                    raise WorkflowPlanError(
                        f"StateWork {statework_id!r} has a malformed completion claim class")
                normalized[claim_class] = {
                    "minimum_state": minimum_state,
                    "evidence_kinds": list(evidence_kinds),
                }
            if normalized:
                completion_claim_classes[statework_id] = normalized
        registry_version = str(self.compiled.get("registry_version") or
                               self.compiled.get("version") or "")
        registry_hash = str(self.compiled.get("registry_hash") or "")
        route_contract_digests: dict[str, str] = {}
        for item in active:
            selected = item.get("selected_flow")
            workflow_id = str(item.get("id") or "")
            if (not isinstance(selected, (list, tuple)) or len(selected) != 2
                    or not workflow_id):
                continue
            relative_path, digest = str(selected[0]), str(selected[1])
            route_name = Path(relative_path).parent.name
            route_id = f"flow:{workflow_id}:{route_name}"
            if (not route_name or len(route_id) > 192
                    or len(digest) != 64
                    or any(char not in "0123456789abcdef" for char in digest)):
                raise WorkflowPlanError(
                    "resolved workflow contains a malformed route contract pin")
            route_contract_digests[route_id] = digest
        return {"execution_order": ordered, "active_workflows": active,
                "capsules": capsules,
                "component_requirements": list(dict.fromkeys(component_requirements)),
                "component_enhancements": list(dict.fromkeys(component_enhancements)),
                "route_contract_digests": route_contract_digests,
                "completion_claim_classes": completion_claim_classes,
                "registry_version": registry_version,
                "registry_hash": registry_hash,
                "dependency_checks_passed": True}

    def rank_legal_routes(self, runtime_identity: Mapping[str, Any],
                          task_context: Mapping[str, Any], statework_id: str,
                          candidate_routes: Iterable[str],
                          expected_workflow_revision: int,
                          state_authority: Any) -> dict[str, Any]:
        """Rank child flow routes using CSW contracts and live workflow state."""
        statework_id = str(statework_id or "")
        if not statework_id or len(statework_id) > 64:
            raise WorkflowPlanError("route ranking requires a bounded StateWork ID")
        if type(expected_workflow_revision) is not int or expected_workflow_revision < 0:
            raise WorkflowPlanError("route ranking requires a valid workflow revision")
        routes = tuple(candidate_routes)
        if (not routes or len(routes) > 16 or len(routes) != len(set(routes))
                or any(not isinstance(route, str) or len(route) > 192
                       for route in routes)):
            raise WorkflowPlanError("route ranking candidates are malformed")
        flow_names: dict[str, str] = {}
        for route in routes:
            parts = route.split(":", 2)
            if (len(parts) != 3 or parts[0] != "flow" or parts[1] != statework_id
                    or not parts[2] or len(parts[2]) > 64
                    or any(char in parts[2] for char in "/\\\0")):
                raise WorkflowPlanError("route ranking candidate is outside the target StateWork")
            flow_names[route] = parts[2]

        inspect = getattr(state_authority, "inspect_workflow", None)
        if not callable(inspect):
            raise WorkflowPlanError("route ranking requires a bound workflow state authority")
        subject_refs = task_context.get("statework_subject_refs") or {}
        subject_ref = (subject_refs.get(statework_id)
                       if isinstance(subject_refs, Mapping) else None)
        subject_ref = str(subject_ref or runtime_identity.get("subject_ref") or "")
        if not subject_ref:
            raise WorkflowPlanError("route ranking requires a scoped workflow subject")
        entry = self.entries.get(statework_id)
        if entry is None:
            raise WorkflowPlanError(f"StateWork {statework_id!r} is unavailable")
        engine = entry.get("engine") or {}
        contract_hash = str(engine.get("contract_hash") or "")
        if not contract_hash:
            raise WorkflowPlanError(f"StateWork {statework_id!r} has no compiled workflow contract")
        snapshot = inspect(statework_id=statework_id, subject_ref=subject_ref,
                           contract_hash=contract_hash)
        actual_revision = getattr(snapshot, "revision", None)
        if actual_revision != expected_workflow_revision:
            raise WorkflowPlanError("workflow revision changed before route ranking")

        flow_contract = self._compiled_flow_metadata(statework_id)
        manifest = self.manifests[statework_id]
        selection_context = self._flow_context(task_context)
        selection_context["current_state"] = getattr(snapshot, "current_state", None)
        selection = FlowSelector.select(
            flow_contract, selection_context,
            dict(manifest.get("flow_selection") or {}))
        eligible = set(selection.candidates)
        score_by_name = dict(selection.scores)
        legal_routes = tuple(sorted(
            route for route, flow_name in flow_names.items()
            if flow_name in eligible and flow_name in score_by_name))
        scores = {route: int(score_by_name[flow_names[route]])
                  for route in legal_routes}
        file_hashes = entry.get("file_hashes") or {}
        route_digests = {}
        for route in legal_routes:
            flow_name = flow_names[route]
            digest = file_hashes.get(f"flows/{flow_name}/flow.md")
            if (not isinstance(digest, str) or len(digest) != 64
                    or any(char not in "0123456789abcdef" for char in digest)):
                raise WorkflowPlanError(
                    f"StateWork {statework_id!r} has no compiled pin for flow {flow_name!r}")
            route_digests[route] = digest
        registry_hash = str(self.compiled.get("registry_hash") or "")
        if not registry_hash:
            raise WorkflowPlanError("compiled workflow registry has no integrity hash")
        return {"legal_routes": legal_routes, "scores": scores,
                "workflow_revision": actual_revision,
                "route_contract_digests": route_digests,
                "registry_hash": registry_hash,
                "workflow_id": statework_id}

    @staticmethod
    def _collect_component_integrations(integrations: Any,
                                        required: list[str],
                                        enhanced: list[str]) -> None:
        """Normalize CFW component requirements while CSW owns manifest meaning."""
        if integrations is None:
            return
        if not isinstance(integrations, Mapping):
            raise WorkflowPlanError("StateWork integrations must be a mapping")
        cfw = integrations.get("cognitiveframeworks") or {}
        if not isinstance(cfw, Mapping):
            raise WorkflowPlanError("CognitiveFrameworks integration must be a mapping")
        for field, destination in (("required", required), ("enhancements", enhanced)):
            values = cfw.get(field) or ()
            if not isinstance(values, (list, tuple)) or len(values) > 64:
                raise WorkflowPlanError(f"CognitiveFrameworks {field} list is invalid")
            for value in values:
                if not isinstance(value, str) or not value or len(value) > 128:
                    raise WorkflowPlanError(
                        f"CognitiveFrameworks {field} contains an invalid component ID")
                if value not in destination:
                    destination.append(value)

    def _pin_workflow(self, statework_id: str, manifest: Mapping[str, Any],
                      entry: Mapping[str, Any], owner_root: Path,
                      flow_context: Mapping[str, Any], requested: Optional[str],
                      excluded_flows: set[str], preferred_specialists: set[str],
                      suppressed_specialists: set[str]) -> dict[str, Any]:
        flow_metadata = self._compiled_flow_metadata(statework_id)
        engine = dict(entry.get("engine") or {})
        capsule_text = str(entry.get("runtime_capsule") or "")
        capsule_hash = str(entry.get("runtime_capsule_hash") or "")
        if (not capsule_text or hashlib.sha256(capsule_text.encode()).hexdigest()
                != capsule_hash):
            raise WorkflowPlanError(f"StateWork {statework_id!r} runtime capsule is invalid")
        capsules = {f"statework:{statework_id}": (capsule_text, capsule_hash)}
        composition = composition_for(manifest)
        item = {
            "id": statework_id,
            "version": str(manifest.get("version") or "0.0.0"),
            "domain": str(manifest.get("domain") or ""),
            "purpose": str(manifest.get("purpose") or ""),
            "entrypoint": manifest.get("entrypoint"),
            "manifest_hash": str((entry.get("file_hashes") or {}).get("manifest.yaml") or ""),
            "workflow_engine_kind": str(engine.get("kind") or "state_machine"),
            "workflow_contract_version": str(engine.get("contract_version") or ""),
            "workflow_contract_hash": str(engine.get("contract_hash") or ""),
            "runtime_hash": capsule_hash,
            "flow_selection": dict(manifest.get("flow_selection") or {}),
            "composition": {
                "group": composition["group"],
                "mode": composition["mode"],
                "requires": sorted(composition["requires"]),
                "conflicts": sorted(composition["conflicts"]),
            },
            "exclusive_group": (composition["group"]
                                if composition["mode"] == "exclusive" else None),
            "integrations": dict(manifest.get("integrations") or {}),
            "selected_flow": None,
        }
        flows_dir = owner_root / "flows"
        flow_paths = sorted(flows_dir.glob("*/flow.md")) if flows_dir.is_dir() else []
        selected_path: Optional[Path] = None
        specialists: list[tuple[Path, str]] = []
        if flow_paths:
            selection = FlowSelector.select(
                flow_metadata, flow_context, item["flow_selection"],
                requested=requested, excluded=excluded_flows)
            if selection.selected is None:
                if selection.reason == "error":
                    raise WorkflowPlanError(
                        f"StateWork {statework_id!r} flow selection is ambiguous")
                if selection.reason == "requested_ineligible":
                    raise WorkflowPlanError(
                        f"StateWork {statework_id!r} requested flow {requested!r} is ineligible")
                if selection.reason == "blocked":
                    raise WorkflowPlanError(
                        f"StateWork {statework_id!r} has no eligible flow")
                item["flow_selection_status"] = "inactive"
            else:
                selected_path = flows_dir / selection.selected / "flow.md"
                selected_path.resolve().relative_to(owner_root)
                flow_name = selected_path.parent.name
                metadata = flow_metadata[flow_name]
                flow_text = selected_path.read_text(encoding="utf-8")
                flow_hash = hashlib.sha256(flow_text.encode()).hexdigest()
                capsules[f"statework-flow:{statework_id}:{flow_name}"] = (flow_text, flow_hash)
                required = list(metadata.get("required_specialists") or ())
                optional = list(metadata.get("optional_specialists") or ())
                budget = {"low": 1, "medium": 2, "high": 3}.get(
                    manifest.get("context_budget", "medium"), 2)
                optional.sort(key=lambda value: (str(value) not in preferred_specialists,
                                                 str(value)))
                candidates = [(str(value), True) for value in required]
                candidates.extend((str(value), False) for value in optional)
                for relative, is_required in candidates:
                    if relative in suppressed_specialists or Path(relative).name in suppressed_specialists:
                        if is_required:
                            raise WorkflowPlanError(
                                f"required specialist {relative!r} cannot be suppressed")
                        continue
                    if not is_required and len(specialists) >= budget:
                        continue
                    path = (selected_path.parent / relative).resolve()
                    path.relative_to(owner_root)
                    if not path.is_file():
                        raise WorkflowPlanError(
                            f"StateWork {statework_id!r} specialist {relative!r} is missing")
                    text = path.read_text(encoding="utf-8")
                    specialists.append((path, hashlib.sha256(text.encode()).hexdigest()))
                item["flow_integrations"] = dict(metadata.get("integrations") or {})
                item["flow_metadata"] = {
                    key: metadata.get(key)
                    for key in ("flow", "when", "integrations", "required_specialists",
                                "optional_specialists", "completion", "fallback")
                    if key in metadata
                }
                item["selected_flow"] = [
                    f"{statework_id}/{selected_path.relative_to(owner_root).as_posix()}",
                    flow_hash]
        for index, (path, content_hash) in enumerate(specialists):
            text = path.read_text(encoding="utf-8")
            capsules[f"statework-specialist:{statework_id}:{index}"] = (text, content_hash)
        item["selected_specialists"] = [
            [f"{statework_id}/{path.relative_to(owner_root).as_posix()}", digest]
            for path, digest in specialists
        ]
        item["_capsules"] = capsules
        return item
