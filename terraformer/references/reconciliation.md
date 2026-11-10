# Contract reconciliation: interfaces and assumptions

Inventory components by identity, effective version, protocol, endpoints/ports (conceptually), actual runtime availability, config, and readiness. Contract comparisons must include data shapes, nullability, ordering, errors, version negotiation, timeouts, retry ownership, backpressure, idempotency, cancellations, security trust/identity, consistency, and upgrade strategy **where relevant**.

Build an edge-by-edge compatibility matrix: producer version/guarantees, consumer expectation, observed evidence, incompatibility cause, required adapter, owner of adaptation, rollback. Avoid introducing a universal adapter layer unless the observed interface set truly justifies it.

`INCOMPATIBLE` is preferable to false alignment. An interface that exists in source but is never exercised by the actual consumer is not `CONTRACTS_VALIDATED`. A contract reconciliation must be proven against both endpoints (or explicitly blocked if unavailable).
