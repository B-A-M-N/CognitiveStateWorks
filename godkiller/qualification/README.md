# GodKiller — qualification obligations

Qualification has two layers. `tests/validate.py` checks local schema, packet, transition, flow, and scenario consistency. `../tests/test_architecture_workflow_qualification.py` exercises GodKiller through CSW's compiled `WorkflowAuthority`, including host-attested evidence, revision conflicts, consequential-evidence freshness, invalidation, and recovery. These tests qualify CSW enforcement behavior; they do not determine whether an architectural boundary is correct in an arbitrary product.

## Required acceptance matrix

Use `cases.yaml` as a set of architecture-neutral adversarial briefs. For each case capture actual subject revision, initial/terminal state, intended invariants, before/after dependency and owner maps, executed oracle, evidence provenance, and a negative case that must not accidentally qualify. Include both justified extraction and no-decomposition outcomes across monolith, event-driven, plugin, and concurrent shared-state shapes.

## Negative gates

- Missing baseline or unreachable component prevents consequential success.
- Agent-reported or stale evidence cannot mint host-attested successful transitions.
- Unauthorized edit is denied before mutation; no automatic grant.
- Concurrent state updates cannot silently overwrite a newer revision; demonstrate CAS conflict.
- Recovery does not claim success merely from a rollback command; observe restored invariants.
- A cosmetic extraction/central coordinator recreation or a component that passes alone but fails when connected cannot qualify.
- A negative diagnosis or a no-integration-needed verdict must be accepted with actual supporting proof.

## Current CSW integration and remaining qualification

The bundle is registered in the repository's compiled registry and has a global packet fixture. Run the focused host qualification with `python3 -m pytest -q -p no:cacheprovider tests/test_architecture_workflow_qualification.py`, plus `python3 tests/validate-stateworks.py`. Host-issued observations in these tests prove the authority gate and legal-transition path. Domain-specific architecture claims still require real subject evidence, independent behavioral oracles, and human/operator review; the fixtures do not establish architectural correctness.

There is intentionally **no automatic installation and no cross-skill prerequisite**. For advisory-only use, use `SKILL.md`; do not claim enforcing semantics.
