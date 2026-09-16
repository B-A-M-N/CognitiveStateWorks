# Policy: Evidence Thresholds

Evidence strength must match the claim. This policy sets the minimum rung
(from the evidence ladder in `primitives/evidence/`) required per claim class.

| Claim | Minimum evidence |
|---|---|
| "Configured" | config exists + declared state observed (rung 1–2) |
| "Deployed" | effective state observed running the new version (rung 4) |
| "Fixed" | failure reproduces before, passes after (rung 5) |
| "Resilient to X" | X actually injected; behavior observed (rungs 5–7) |
| "Recoverable" | restore/failover executed and verified end-to-end (rungs 6–8) |
| "Capacity adequate" | load evidence at expected peak + failure headroom (rungs 6–7) |
| "Performant" | component-level latency decomposition, baseline vs after, percentiles (rungs 5–7) |
| "Production ready" | readiness review across all dimensions, envelope declared, integration + load + failure + recovery evidence |
| "Root cause: X" | mechanism identified — correlation alone never suffices |

## Interpretation rules

- The thresholds are floors, not targets: stronger evidence is always acceptable, weaker never passes.
- When the minimum rung is unavailable (e.g., cannot inject host failure in production), the claim is stated as unverified with the gap explicit — never silently downgraded.
- Test-infrastructure evidence must carry its production-equivalence caveats or it does not count toward the rung.
- Do not fabricate evidence that was not collected. Report unknown as unknown.

This policy binds the Validate flow's pass/fail calls, the Assess flow's
readiness classification, and the Evidence Packet's honesty.
