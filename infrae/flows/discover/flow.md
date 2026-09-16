---
flow: discover
operations: [observe, inspect, discover]
triggers: [observation, observe]
states:
  from: [UNKNOWN, OBSERVED]
  through: [OBSERVED]
framework_requirements: [owl, anchor]
required_specialists: []
optional_specialists: []
---
# Flow: Discover (UNKNOWN → OBSERVED)

Purpose: establish infrastructure truth. Read-only.

## Steps

1. Enumerate components: nodes, services, networks, storage, control planes, data planes, external dependencies.
2. Enumerate runtime state, not just configuration: what is actually running, where, at what version.
3. Identify environment: name, purpose, production-criticality, ownership.
4. Inspect configuration **and** configuration drift (manual changes, emergency fixes, partial rollouts, version skew, unmanaged resources).
5. Inspect topology and dependency graph (see `../../primitives/dependency-graph/`).
6. Identify unknowns explicitly. Unknowns are acceptable; hidden unknowns are not.

## Critical rules

> Discovery must not silently mutate the thing being discovered.

- Distinguish declared / observed / effective / dependency / failure / recovery state (see `../../primitives/state-ownership/`). Disagreement between them is a finding, not noise.
- Do not reason from configuration files alone: `code exists ≠ runtime matches code`.
- Uncertainty is itself sufficient reason to run this flow.

## Output (handoff packet)

Emit the typed handoff packet in the common envelope
(`../..//schemas/handoff-packet.schema.json`, composed by
`../../schemas/infrastructure-truth-packet.schema.json`). Domain data lives
in `payload`; envelope fields are canonical and never re-declared:

```yaml
packet_id:
packet_type: infrastructure_truth_packet
schema_version:
producer: infrae
task_id:
subject_ref:
observed_at:
input_state:
output_state: observed
evidence_refs:
unknowns:
blockers:
authority:
invalidated_by:
recommended_next:

payload:
  state: observed
  components: ...
  topology: ...
  configuration: ...
  effective_state: ...
  unknowns: ...
  confidence: ...
```

Network failures frequently masquerade as application failures — when connectivity behavior is uncertain, inspect name resolution, routing, reachability, firewall, NAT, proxy chain, TLS, MTU, packet loss, port exhaustion before jumping to application logic.
