# Architecture Boundary Packet (ABP) v1 — semantic interpretation

The `architecture_boundary` payload is **technology-neutral**. It is an observation and transfer artifact, not a command to use any particular language, framework, deployment shape, or design pattern.

## Required facts

- `subject`: stable identity, observed revision, artifact kind, fingerprint, and observation time. A symbolic revision must map unambiguously to the observed object.
- `baseline`: public behavior contracts and independent test/observation oracles. A missing baseline is a stop condition for consequential edits, not permission to invent one.
- `responsibilities`: independently describable obligations with current and proposed owners. A proposed owner is **not** proof of actual ownership.
- `components` and `interfaces`: verifiable boundaries and versioned interaction contracts, including failure semantics.
- `ownership_map`: for every authoritative mutable resource, explicit ownership mode, owners, and (for shared/coordinated authority) protocol/conflict resolution.
- `dependency_edges`: direction and reason; document cycles, hidden runtime access, and dynamic wiring when observable.
- `lifecycle_contracts`: prerequisites, startup/order, cancellation, failure, recovery, and teardown, as applicable.
- `invariants`: statements that must survive transformation. High-risk invariants require independent oracles.
- `migration`: incremental steps, compatibility requirements, and rollback strategy.
- `verification`: claim-specific checks, statuses, and evidence references. `pass` means the relevant oracle actually ran against the observed revision.
- `unresolved`: unknowns and blocking ambiguity, not silently assumed conclusions.

## Semantic gates beyond JSON Schema

JSON Schema validates **shape only**. A trusted host/qualified evaluator must also enforce:

1. References resolve to the same observed subject and applicable revision; evidence is authentic, scoped, and fresh.
2. IDs are unique within their namespaces; all cross-references resolve. No phantom component or interface.
3. Each mutable resource with authority has exactly one exclusive owner **or** a documented, verifiable coordinated-sharing protocol. `external` requires a named external authority.
4. Each dependency points to existing components and has a contract or consciously documented boundary exception.
5. No migration step is marked safe without independently observed rollback feasibility and compatibility constraints.
6. Claimed `pass` requires qualified evidence tied to the exact test oracle and revision. Self-attestation by the editor is insufficient.
7. An absent/null owner, incompatible versions, unexplained side effect, unresolved critical issue, or stale fingerprint blocks applicable consequential transitions.
8. A new subject revision, contradictory observation, or changed interface/lifecycle/ownership invalidates dependent conclusions. Re-observe only affected facts, but never reuse stale evidence.

The host owns storage, evidence attestation, freshness, and concurrency-safe transition commits. A skill does not create a second state database or bypass host authorization.

## Interchange and independence

Any competent human or tool may supply the `architecture_boundary` payload with verifiable provenance. The receiving skill validates it, does not trust its declared verdict blindly, and re-observes facts required by its own goals. No StateWork invokes another StateWork directly. Partial work can be integrated and then more decomposition attempted.
