# Testing: Snapshot / Golden Tests

Layer 4. Strong regression evidence for rendered surfaces. They **do not**
prove interaction semantics by themselves.

Deterministic inputs required: terminal dimensions, color profile, data,
timestamps, animation state. Any nondeterminism poisons the goldens. Pair
with layout invariant assertions (`../layout-tests/`) — a snapshot can match
while violating an invariant.
