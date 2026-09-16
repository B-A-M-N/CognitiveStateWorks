---
flow: decommission
required_specialists: []
optional_specialists: []
---
# Flow: Decommission (any state → RETIRED)

Decommissioning is a production change, not cleanup. It can be destructive.

## Pipeline

```text
candidate → consumer discovery → dependency confirmation → traffic zero
→ state migration → credential revocation → observability removal
→ retention / backup decision → destroy → verify absence
```

## Checklist before removal

```text
traffic      = zero or intentionally redirected
consumers    = none (verified, not assumed)
state        = migrated or intentionally destroyed
credentials  = revoked
routes       = updated
DNS          = updated (TTL, resolver caching, negative caching, stale clients)
monitoring   = updated
backups      = handled (retention decision explicit)
rollback window = understood
```

## Hidden consumers

Unknown consumers are a reason to stop, not a reason to proceed carefully.
Search for hidden dependencies before removal (shared credentials, DNS,
queues, API quotas, startup ordering — see the Model flow's hidden-dependency
list). A decommission may legally end in:

```text
BLOCKED: unknown consumer exists
```

rather than guessing.

## After destruction

Verify absence: no residual traffic, no residual alerts, no orphaned state,
no stale service discovery entries, credentials confirmed dead. Record the
Infrastructure Evidence Packet (`../../primitives/evidence/`) — decommission
history answers "what used to live here?" questions for years.
