# Boundary selection: cohesion, authority, independence

**Candidate boundary:** one stable reason to change, one explicit authority over owned transitions, a small public interface, and a test oracle independent of the original host. Boundaries may live within one source file or process; separate deployment is not required.

For every candidate answer: What does it own? What does it read? What may it mutate? What data does it publish? What error/cancel/retry semantics are visible? Who initializes/tears it down? What is the version/compatibility policy? How can we prove it is isolated?

## Partition decision record

- Candidate alternatives: retain hub, split responsibility, extract pure policy, use owned state service, etc. Avoid automatically favoring more components.
- Every authoritative mutable resource is exclusive **or** coordinated under an explicit protocol. 'Shared by convenience' is not a legal ownership definition.
- Dependencies must point through contracts. If a cycle is unavoidable, document why and prove finite lifecycle/ownership behavior.
- Keep control planes thin: wiring/composition may coordinate lifecycle without absorbing each domain's decisions or mutable state.
- Old caller adapters may be transitional, but they may not permanently preserve unconstrained access to extracted internals.

## Fake decomposition detector

Red flags: extracted classes still receive the original giant context/object; new modules directly mutate one global dict or singleton; coordinator forwards every domain method; modules trade callbacks with no ownership boundaries; all tests instantiate the old God Object to access anything; same cross-responsibility change touches every new component; duplicate caches become authoritative.

Reject or replan these unless independently justified by evidence. A larger number of files, types, and indirection is not a success metric.
