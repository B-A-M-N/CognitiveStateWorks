#!/usr/bin/env python3
"""Validated packet and transition primitives for CognitiveStateWork."""
from __future__ import annotations

import json
import copy
import fcntl
import hashlib
import inspect
from importlib import metadata
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional
from datetime import datetime, timezone

import jsonschema
import yaml
from importlib.resources import files as resource_files
if __package__:
    from .workflow_engines import (EngineRegistry, MilestoneWorkflowEngine,
                                   StateMachineWorkflowEngine, WorkflowDecision,
                                   WorkflowIdentity, WorkflowProgressFact,
                                   WorkflowSnapshot)
    from .flow_selectors import FlowSelector
else:
    from workflow_engines import (EngineRegistry, MilestoneWorkflowEngine,
                                  StateMachineWorkflowEngine, WorkflowDecision,
                                  WorkflowIdentity, WorkflowProgressFact,
                                  WorkflowSnapshot)
    from flow_selectors import FlowSelector

if __package__:
    from .errors import PacketValidationError, TransitionError
    from .resources import (EVIDENCE_KIND_REGISTRY_PATH, ROOT, _aware_datetime,
                            _CHECKOUT_ROOT, _CODE_ROOT, _PACKAGED_BUILTIN_ROOT,
                            _load_yaml, _local_schema_registry, _package_resource,
                            _schema_resource, _schema_text, load_evidence_kind_registry,
                            load_packet_registry, render_runtime_capsule)
    from .evidence import (EVIDENCE_VALIDATORS, FRESHNESS_VALIDATORS,
                           EvidenceStore, EvidenceValidatorRegistry,
                           FreshnessValidatorRegistry, TrustedValidatorRegistry,
                           _path_value, _repository_truth_v1,
                           _trusted_validator_hash, evaluate_freshness)
else:
    from errors import PacketValidationError, TransitionError
    from resources import (EVIDENCE_KIND_REGISTRY_PATH, ROOT, _aware_datetime,
                           _CHECKOUT_ROOT, _CODE_ROOT, _PACKAGED_BUILTIN_ROOT,
                           _load_yaml, _local_schema_registry, _package_resource,
                           _schema_resource, _schema_text, load_evidence_kind_registry,
                           load_packet_registry, render_runtime_capsule)
    from evidence import (EVIDENCE_VALIDATORS, FRESHNESS_VALIDATORS,
                          EvidenceStore, EvidenceValidatorRegistry,
                          FreshnessValidatorRegistry, TrustedValidatorRegistry,
                          _path_value, _repository_truth_v1,
                          _trusted_validator_hash, evaluate_freshness)


if __package__:
    from .state_store import PacketStore, SubjectStateStore
    from .selection_store import WorkflowSelectionStore
    from .transition_engine import PROGRESS_CLASSES, TransitionDecision, TransitionEngine
    from .workflow_controller import StandaloneStateWorkController
    from .workflow_authority import WorkflowAuthority, WorkflowAuthorityIdentity
    from .standalone_host import StandaloneHostInterface
else:
    from state_store import PacketStore, SubjectStateStore
    from selection_store import WorkflowSelectionStore
    from transition_engine import PROGRESS_CLASSES, TransitionDecision, TransitionEngine
    from workflow_controller import StandaloneStateWorkController
    from workflow_authority import WorkflowAuthority, WorkflowAuthorityIdentity
    from standalone_host import StandaloneHostInterface


def load_compiled_registry(root: Optional[Path] = None, *,
                           verify_bundles: bool = True) -> Dict[str, Any]:
    """Load the compiled registry through the dedicated registry module."""
    if __package__:
        from .registry import load_compiled_registry as implementation
    else:
        from registry import load_compiled_registry as implementation
    return implementation(root, verify_bundles=verify_bundles)


def open_compiled_registry(root: Optional[Path] = None, *,
                           verify_bundles: bool = True) -> Any:
    """Open the verified registry with CSW's canonical flow services."""
    if __package__:
        from .registry import open_compiled_registry as implementation
    else:
        from registry import open_compiled_registry as implementation
    return implementation(root, verify_bundles=verify_bundles)


def __getattr__(name: str) -> Any:
    if name == "RegistryCompiler":
        if __package__:
            from .registry import RegistryCompiler
        else:
            from registry import RegistryCompiler
        return RegistryCompiler
    raise AttributeError(name)
