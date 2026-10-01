"""Bounded, data-only StateWork flow selector shared by all CFW routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


MAX_DEPTH = 8
MAX_NODES = 64
MAX_CHILDREN = 16
MAX_VALUES = 16
ROUTING_FIELDS = frozenset({
    "operation", "trigger", "task_shape", "phase", "domain_tags",
    "current_state",
})


@dataclass(frozen=True)
class FlowSelection:
    candidates: tuple[str, ...]
    selected: Optional[str]
    scores: Mapping[str, int]
    reason: str


class FlowSelector:
    """Evaluate bounded predicates and apply a bundle's declared route policy."""

    @staticmethod
    def validate_predicate(predicate: Any) -> None:
        nodes = 0

        def visit(node: Any, depth: int) -> None:
            nonlocal nodes
            nodes += 1
            if nodes > MAX_NODES or depth > MAX_DEPTH:
                raise ValueError("flow selector exceeds its complexity bound")
            if not isinstance(node, Mapping):
                raise ValueError("flow selector nodes must be mappings")
            if len(node) == 1 and next(iter(node)) in {"all", "any"}:
                key = next(iter(node))
                children = node[key]
                if (not isinstance(children, list) or not children
                        or len(children) > MAX_CHILDREN):
                    raise ValueError(f"flow selector {key} must contain 1..{MAX_CHILDREN} nodes")
                for child in children:
                    visit(child, depth + 1)
                return
            if set(node) == {"not"}:
                visit(node["not"], depth + 1)
                return
            if set(node) != {"field", "in"}:
                raise ValueError("flow selector leaves require only field and in")
            field, values = node.get("field"), node.get("in")
            if field not in ROUTING_FIELDS:
                raise ValueError(f"unsupported flow routing field {field!r}")
            if (not isinstance(values, list) or not values or len(values) > MAX_VALUES
                    or any(not isinstance(value, str) or not value or len(value) > 128
                           for value in values)
                    or len(set(values)) != len(values)):
                raise ValueError("flow selector in must contain bounded unique strings")

        visit(predicate, 1)

    @staticmethod
    def _evaluate(predicate: Any, context: Mapping[str, Any], depth: int = 1
                  ) -> tuple[Optional[bool], int]:
        if depth > MAX_DEPTH or not isinstance(predicate, Mapping):
            return False, 0
        if len(predicate) == 1 and "all" in predicate:
            results = [FlowSelector._evaluate(node, context, depth + 1)
                       for node in predicate["all"]]
            if any(value is False for value, _score in results):
                return False, 0
            known = [(value, score) for value, score in results if value is not None]
            return (True, sum(score for _value, score in known)) if known else (None, 0)
        if len(predicate) == 1 and "any" in predicate:
            results = [FlowSelector._evaluate(node, context, depth + 1)
                       for node in predicate["any"]]
            matches = [score for value, score in results if value is True]
            if matches:
                return True, max(matches)
            if any(value is None for value, _score in results):
                return None, 0
            return False, 0
        if set(predicate) == {"not"}:
            value, _score = FlowSelector._evaluate(predicate["not"], context, depth + 1)
            return (None, 0) if value is None else (not value, 0)
        field = str(predicate.get("field") or "")
        if field not in context or context[field] is None:
            return None, 0
        actual = context[field]
        expected = predicate.get("in")
        if isinstance(actual, (list, tuple, set, frozenset)):
            matched = bool(set(actual) & set(expected or ()))
        else:
            matched = actual in (expected or ())
        return matched, int(matched)

    @classmethod
    def evaluate(cls, predicate: Any, context: Mapping[str, Any]) -> tuple[bool, int]:
        cls.validate_predicate(predicate)
        result, score = cls._evaluate(predicate, context)
        # Missing context is deliberately neutral: an explicit route can still
        # be honored before the host has observed that routing dimension.
        return result is not False, score

    @classmethod
    def select(cls, flows: Mapping[str, Mapping[str, Any]], context: Mapping[str, Any],
               policy: Mapping[str, Any], *, requested: Optional[str] = None,
               excluded: Optional[set[str]] = None) -> FlowSelection:
        fallback_policy = str(policy.get("fallback", "required"))
        no_match = str(policy.get("no_match", "blocked"))
        ambiguity = str(policy.get("ambiguity", "error"))
        if fallback_policy not in {"required", "optional", "forbidden"}:
            raise ValueError("invalid flow fallback policy")
        if no_match not in {"inactive", "blocked"} or ambiguity != "error":
            raise ValueError("invalid flow ambiguity or no-match policy")
        excluded = excluded or set()
        candidates: list[tuple[int, str]] = []
        fallbacks: list[tuple[int, str]] = []
        for name, metadata in flows.items():
            fallback = metadata.get("fallback") is True
            if name in excluded:
                continue
            when = metadata.get("when")
            if when is None:
                matched, score = True, 0
            else:
                matched, score = cls.evaluate(when, context)
            if not matched:
                continue
            (fallbacks if fallback else candidates).append((score, name))
        if requested is not None:
            eligible = {name for _score, name in candidates + fallbacks}
            if requested not in eligible:
                return FlowSelection(tuple(sorted(eligible)), None, {}, "requested_ineligible")
            score_map = {name: score for score, name in candidates + fallbacks}
            return FlowSelection(tuple(sorted(eligible)), requested, score_map, "requested")
        if not candidates:
            candidates = fallbacks
        if not candidates:
            return FlowSelection((), None, {}, no_match)
        top_score = max(score for score, _name in candidates)
        winners = tuple(sorted(name for score, name in candidates if score == top_score))
        score_map = {name: score for score, name in candidates}
        if len(winners) != 1:
            return FlowSelection(tuple(sorted(name for _score, name in candidates)),
                                 None, score_map, ambiguity)
        return FlowSelection(tuple(sorted(name for _score, name in candidates)),
                             winners[0], score_map, "selected")


__all__ = ["FlowSelector", "FlowSelection", "ROUTING_FIELDS"]
