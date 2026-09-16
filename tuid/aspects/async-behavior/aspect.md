# Aspect: Async Behavior

Background work must not freeze interaction unnecessarily.

## Model

```text
request initiated → pending state → background operation
→ result event → state transition
```

Consider: cancellation · stale completion · duplicate request · retry ·
timeout · progress · failure · shutdown.

## Stale results

```text
User selects Host A → request A starts
User selects Host B → request B starts
request A completes last
```

Do not accidentally render Host A as though it remains current. **Associate
async results with the state/request that produced them.** Common async race
displaying wrong data is HIGH severity.

## Contracts

- Effects execute outside the render path; results return as events through controlled state transitions — never by painting the terminal directly.
- Synchronous network work in the interaction path is an anti-pattern.
- A background operation may update application state but may not corrupt render ownership (`../rendering/`).
- Async blocking/cancellation/stale-results are audit dimensions (`../../flows/review/`).
