# Lifecycle and failure composition

Define directed lifecycle graph: construction, initialization, readiness, normal execution, cancellation, drain, teardown, recovery. State which component owns each phase and how dependents learn readiness/failure.

Required contract questions: Can init be retried? What if dependency B fails after A starts? When does C accept work? Who propagates cancellation? Who releases resources on partial startup? Is termination idempotent? Can it recover after restart? What if a message is duplicated, delayed, dropped, or delivered out of order? Is rolling compatibility required?

In a synchronous library system, a single call-stack contract may be sufficient. In concurrent services, provide deadlines, backpressure, retry ownership, and idempotency. In plugin ecosystems, provide isolation, version negotiation, deactivation/reload, and fault boundaries. Do not prescribe these features where no relevant threat model exists.

Proof means exercising failure and reentry, not just documenting an order. Durable state should not depend on one coordinator's ephemeral memory unless explicitly warranted by the domain contract.
