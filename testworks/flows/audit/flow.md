---
flow: audit
required_specialists: []
optional_specialists: []
when:
  field: operation
  in:
  - audit
---
# Audit flow

**Purpose.** Evaluate the portfolio for actual risk detection, distinctiveness and maintenance cost.

## Steps
1. Classify tests CRITICAL_INVARIANT, UNIQUE_REGRESSION, USEFUL_EXPENSIVE, REDUNDANT, FLAKY, OBSOLETE, or UNPROVEN_VALUE.
2. Record evidence for each label; never invent an opaque aggregate quality score.
3. For expensive but valuable cases, first consider selective scheduling and isolation-safe parallelism.
4. Flag weak or obsolete assertions, duplicated fixtures and nondeterministic cases for investigation.
5. Make keep, selective-run, repair or *proposal*-only consolidation recommendations; do not delete.

## Required outputs
- portfolio classification with supporting receipts
- execution topology suggestions
- candidate remediation list

## Stop / refuse
- Deletion based solely on never failing
- Equating low runtime with high detection value
- Removal without exact purpose and owner

## Boundary
Proposed repository edits are passed to Getter after ownership is established.
