# GodKiller — independently complete architecture StateWork

**Domain:** architectural decomposition. **Version:** 1.0.0. **Host dependence:** optional for advisory skill use; enforcement requires CognitiveStateWorks' trusted runtime and domain-specific host validators.

This bundle can be read as a standalone agent skill via `SKILL.md`. For CSW, place the directory under an explicitly configured trusted bundle root; validate schema/flows/evidence and the host attestations **before compiling it into an active registry**. It does not require the companion bundle or optional CognitiveFrameWorks / DigitalPsychology layers.

## Package contents

- `SKILL.md`: operational skill, scope and completion tests
- `manifest.yaml`, `transitions.yaml`: native CSW metadata and explicit state machine
- `guidance.md`: compact runtime capsule guidance
- `flows/*/flow.md`: individually routed workflow procedures
- `contracts/`: evidence kinds, packet declarations, JSON Schema and ABP semantics
- `references/`: substantive, independently usable methods and proof requirements
- `templates/`: architecture packet, assessment and evidence/plan templates
- `qualification/`: cross-architecture acceptance and adverse scenarios
- `tests/validate.py`: executable bundle self-check (Python+PyYAML+jsonschema only for **authoring validation**; product architecture remains language-neutral)

## Important limits

The bundle's manifest and transition contract **do not install host-side semantic validators**. Host-attested `*.e2e`, `*.boundary_independence`, etc. require trusted implementations to examine actual observations. `tests/validate.py` checks structure and fixtures only. Running it is not a claim of live production or integration correctness.

The shared `architecture-boundary/v1` structure is interchangeable data, not evidence of another StateWork having run. No direct calls, cyclic requirements or shared runtime state authority exist.
