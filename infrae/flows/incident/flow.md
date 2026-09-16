---
flow: incident
required_specialists: []
optional_specialists: []
---
# Flow: Incident (any state → INCIDENT → RECOVERING)

Priority order:

```text
detect → classify impact → bound blast radius → preserve evidence
→ stabilize → restore → verify → diagnose → remediate → prevent recurrence
```

Do not optimize architecture during an active incident unless necessary to
restore safety. Restoration and root-cause analysis are **separate
objectives**.

## Triage packet

```yaml
impact:      { users: services: regions: severity: }
timeline:    { first_seen: change_events: }
symptoms:    { errors: latency: saturation: availability: }
dependencies:{ degraded: unavailable: }
scope:       { expanding: stable: }
mitigation:  { attempted: effective: }
current_state: { stable: degraded: unsafe: }
```

## Evidence preservation

Before destroying diagnostic state, preserve where practical: logs, metrics,
traces, process state, failed configuration, crash data, topology, recent
changes, timestamps. Recovery comes first when necessary — but avoid erasing
all evidence through reflexive restart loops.

## Restart discipline

Restarting is a mitigation, not a diagnosis. Repeated restarts erase
evidence, amplify load, trigger recovery storms, destroy caches, increase
startup traffic, and hide persistent faults. Use restart when it is the
appropriate stabilization mechanism; never confuse it with root-cause
resolution.

## Root-cause status vocabulary

Report `confirmed / probable / unknown`. Correlation is not root cause —
identify the mechanism before claiming cause.

## Standard output

```text
Impact
- ...

Observed
- ...

Most likely failure domain
- ...

Evidence
- ...

Immediate mitigation
- ...

Do not do
- ...

Recovery verification
- ...

Root-cause status
- confirmed / probable / unknown

Follow-up
- ...
```

Distinguish facts from hypotheses throughout. On stabilization, hand to
`../recover/` for full restoration (redundancy, integrity, capacity — not
just liveness).
