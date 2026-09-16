# Domain: Identity

Supplies identity, credential, and trust analysis and actions to Infrae
flows. Does not own state transitions — a secrets specialist knows how to
rotate a credential; whether rotation timing is safe is the Change flow's
call, gated by its blast-radius analysis.

## Covers

Service identities, machine identities, credentials, API keys, certificates,
workload identity, authorization boundaries, secret delivery, secret
rotation, trust roots, signing, mTLS, privilege boundaries.

## Key discipline

**Secrets should be: minimally scoped, attributable, revocable, rotatable,
hidden from logs, delivered securely, and unavailable to unrelated
workloads.** Avoid distributing broad master credentials when narrower
identities exist.

## Secret rotation

Immediate replacement can break clients that have not yet refreshed. A robust
sequence accounts for propagation:

```text
introduce new credential
        ↓
support old + new
        ↓
move clients
        ↓
verify usage
        ↓
revoke old
```

## Certificates

Track issuer, trust root, subject, expiration, renewal, deployment,
revocation, clock skew, and intermediate chain. Certificate renewal is
infrastructure lifecycle, not administrative trivia — expiry is a
predictable outage with a known date.

## Least privilege

Grant only the authority required: filesystem, network, cloud permissions,
database roles, cluster permissions, secret access, host capabilities,
root/admin. Operational convenience is not sufficient justification for
permanent broad privilege.

## Trust boundaries

For each important component identify trusted callers, untrusted callers,
authentication and authorization mechanisms, network boundary, credential
scope, state access, and administrative access. Network location is not
identity; forwarded headers are not authentication. Fail-open vs fail-closed
when the authorization path is unavailable must be a conscious policy
(details in `../security/`).

## Compromise response

Credential compromise is a Recover-flow event with identity-specific steps:
revoke, reissue, audit usage windows, and treat the revocation-propagation
gap as part of the blast radius. Secret rotation to *stop* an active
compromise follows a different sequence than planned rotation — revocation
comes first, breakage second.
