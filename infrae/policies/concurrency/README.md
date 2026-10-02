# Policy: Concurrency

Governs multi-agent and multi-operator infrastructure work. Infrastructure is
global enough that accidental agent concurrency can be destructive.

## Rules

1. Assign ownership boundaries before work begins.
2. Prevent overlapping control of the same mutable resource.
3. Avoid simultaneous changes to shared foundational systems (identity, routing, control plane, shared storage).
4. Declare active change windows.
5. Record current effective state before modification.
6. Use independent staging/test environments when possible.
7. Do not overwrite another worker's emergency mitigation — it may be load-bearing drift.
8. Re-observe state before each critical mutation.
9. Recompute dependency effects after another agent changes shared infrastructure.
10. Keep integration/change authority explicit.

## Standing principles

- A quiet terminal is not evidence a worker has stopped.
- Another worker's reported state is evidence requiring verification, not fact on assertion.
- "It looked fine a moment ago" is not evidence — state moves between messages.
- Operator observations ("traffic is hitting the wrong machine," "that node shouldn't be receiving traffic") are state-invalidating: re-observe before continuing, including mid-mutation.

## FreeInference Acknowledgement

This work benefited in some way from inference provided by [freeinference.org](https://freeinference.org/).

These are independent developments that are not reviewed, endorsed, or sponsored by FreeInference. If you find these projects useful, please consider donating to or sponsoring FreeInference, which provides a vital inference service.
