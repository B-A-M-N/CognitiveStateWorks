# Composed authority and no-new-God-Object safeguards

Ownership map every mutable resource and every policy decision, including cross-component coordination and external authority. `exclusive` means one authoritative writer. `coordinated_shared` requires a concrete, testable protocol for ordering, conflict resolution, failure, and recovery. Read replicas/caches do not become authorities by accident.

Separate concerns:
- **Domain owners:** implement own invariants, local transitions, errors and state.
- **Composition root:** wires dependencies, sets up lifecycle, exposes readiness; it need not make domain decisions.
- **Coordinator (when required):** owns only the cross-component process/transaction invariant it coordinates; does not absorb every component's internal policies.
- **Observability:** correlates events and outcomes; it must not be a shadow state authority.

Reject a 'recomposition' whose new integration manager routes every method and serializes every decision, creates a mega-context holding all writable state, or bypasses published interfaces. Document unavoidable central authority (e.g., a serial transaction ordering point) and test that its scope is narrow and legitimate.
