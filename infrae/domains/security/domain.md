# Domain: Security

Supplies infrastructure security analysis to Infrae flows. Does not own state
transitions — a security specialist identifies boundary findings; whether a
trust-boundary change proceeds is the Change flow's call (HIGH/CRITICAL risk
class).

## Covers

Trust boundaries, proxy/forwarded identity, fail-open vs fail-closed policy,
resource isolation, noisy neighbors, secret handling boundaries.

## Key discipline

**Never trust forwarded metadata solely because a header exists.** Distinguish
physical peer, trusted proxy, forwarded identity, and application client
identity. Trust must derive from an authenticated or explicitly trusted
boundary.

## Security boundaries

For each important component identify: trusted callers, untrusted callers,
authentication mechanism, authorization mechanism, network boundary,
credential scope, state access, administrative access. Avoid relying solely
on network location as identity when stronger identity mechanisms are
available. Credential and identity mechanics live in `../identity/`.

## Fail securely

Where security boundaries are involved, behavior when dependency state is
unknown must be a conscious policy:

```text
authorization service unavailable → fail closed or fail open?
```

Neither answer is universally correct — but "whatever the current code happens
to do" is never acceptable. Document the choice, and verify the implemented
behavior matches it (a fail-closed intent with a fail-open catch block is a
critical finding).

## Trust boundary invariants

Typical infrastructure security invariants:

- Untrusted clients can never directly address internal workers.
- No workload may consume another workload's credentials.
- Admin/control paths are reachable only through authenticated boundaries.
- Secret material never appears in logs, config repos, or metric labels.

## Resource isolation as security

Isolation failures are security failures, not just performance failures:
CPU/memory/GPU/VRAM starvation, file descriptors, process counts, connection
pools, API quotas — a workload that can starve a neighbor can often also
observe or exhaust it. Isolation boundaries should match workload risk.

## Noisy neighbor analysis

When performance is unstable, determine whether unrelated workloads share
constrained resources. Evidence: resource utilization by workload, scheduling
behavior, memory pressure, disk queue, network queue, accelerator occupancy,
API quotas, rate-limit behavior. Sharing a constrained resource is also a
potential lateral-movement path — treat unexplained cross-workload visibility
as a boundary finding.

## Blast radius containment

Security-relevant blast radius questions the Change flow must answer: can
this change expose internal services, widen credential scope, weaken
authentication authority, or create a path around the trust boundary? These
classify the change HIGH/CRITICAL regardless of how small the diff looks.
