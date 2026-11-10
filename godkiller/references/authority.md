# Authority, provenance, and state invalidation

Mutation authority is **not** conferred by the skill being invoked. Identify owner/operator/host authorization for the exact proposed change and required scope. Unknown ownership permits only safe observation or isolated non-destructive experiments.

Store evidence via the existing CSW host evidence store. Host-issued attestations carry kind, validator, issuer, subject_ref, observed_at, digest and trusted provenance. `host:statework-observation` in the bundle is an expected interface declaration, **not a validator implementation**. Host integration must verify the specific architectural claim and fresh subject revision; a general 'agent reported pass' is insufficient.

State and subject revision updates must be concurrency-safe (compare-and-swap). Any new revision, changed owner/resource behavior, invalidated test oracle, or operator-observed contradiction reopens dependent facts. Recover by re-observing affected boundaries, reconciling state, proving rollback/resume, and committing only legal transitions.
