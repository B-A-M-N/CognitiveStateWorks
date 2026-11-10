# TestWorks Operating Guidance

## Assurance-per-effort decision model
Do not invent a universal quality score. Classify test value along independent
axes: failure impact, distinct fault detection, oracle strength, provenance,
maintainability, determinism, runtime/compute cost, and current applicability.
A test that has never failed may still enforce a critical invariant. A test that
fails frequently may merely be broken. Frequency alone determines neither.

**Minimal defensible selection:** identify all non-negotiable invariants, all
plausible regressions introduced by the changed behavior, and every evidence
claim a downstream release gate needs. For each candidate test ask whether a
cheaper existing test reliably detects the same meaningful failure. Choose
smoke/targeted/contract/integration/security/load/endurance as required.
Use full-suite qualification when risk, policy, changed shared semantics, or
insufficient coverage requires it — not because "full" sounds safer.

**Stop rule:** further testing is unjustified once the explicit risk model is
adequately covered at the required confidence, existing receipts are current,
new proposed tests add no defensible detection value, and critical invariants
remain intact. Document scope and uncertainty; zero residual risk is not required.

## Portfolio lifecycle decisions
| Class | Recommendation | Necessary evidence |
| --- | --- | --- |
| CRITICAL_INVARIANT | Keep regardless of low failure rate or cost | policy, impact, invariant ownership |
| UNIQUE_REGRESSION | Keep | unique historical failure or differential mutation/negative case |
| USEFUL_EXPENSIVE | Schedule selectively; do not delete by default | measured cost + retained release gate |
| REDUNDANT | Propose consolidation | equivalent detection/oracle plus retained distinguishing failure modes |
| FLAKY | Diagnose and repair; quarantine only with stated risk | seed/logs/repeats/environment attribution |
| OBSOLETE | Propose removal | retired behavior and ownership confirmation |
| UNPROVEN_VALUE | Investigate; only then propose removal | evidence gaps, proposed replacement, authorization |

Do not use arbitrary deletion quotas or automated "delete all passing duplicates".
When wall-clock duration is the bottleneck, first recommend incremental selection,
parallel execution where isolation is proven, caching compatible with evidence
identity, or separate fast gates and release gates.

## Impact-based test shapes
- LOW: relevant unit/contract tests and narrowly matched prior regressions.
- MODERATE: targeted tests plus boundary and relevant integration evidence.
- HIGH: affected contracts, state/invariant, failure-mode and integration gates.
- CRITICAL: independent safety/security/ownership controls, negative/adversarial
  cases and explicit approval; full or endurance gates if the actual risk warrants.
These are defaults, not substitutes for risk reasoning or organization policy.

## Diagnosis discipline
FAIL is not automatically PRODUCT_DEFECT. Use outcome classes: product regression,
test defect, environmental fault, infrastructure deficiency, flake, and unknown.
Compare repeat runs under controlled inputs only when it adds diagnostic value.
A changed runtime/fixture/seed voids simple equivalence comparisons.

## Change and handoff boundaries
TestWorks owns test *intent* and evidence. Gitter supplies a scoped truth packet
when repository identity/ownership must be established. Getter owns controlled
modifications to tests or other repository state. Infrae owns distributed test
infrastructure and environmental qualification. GodKiller decomposes excessive
responsibility concentration; TerraFormer recomposes architecture. No direct
StateWork-to-StateWork calls. Emit a request for the composition layer.

## Invalidation
Compare claimed and observed state. If SHA, dirty-tree hash, test definitions,
applicable dependency/toolchain/environment assumptions, workload, or required
risk scope change, mark the old claim historical; do not silently reuse it.
Rerun only invalidated evidence where independence is demonstrable. Shared
cross-cutting changes may invalidate multiple receipts and require broader gates.
