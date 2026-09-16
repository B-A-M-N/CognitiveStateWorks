---
flow: migrate
required_specialists: []
optional_specialists: []
---
# Flow: Migrate (dual-state transitions)

Use for: datastore changes, region changes, machine replacement, orchestrator
migration, network redesign, provider migration, schema/storage transition,
state movement.

## The migration state machine

```text
SOURCE_AUTHORITATIVE
       ↓
COMPATIBILITY_READY
       ↓
DUAL_STATE
       ↓
SHADOW_VALIDATED
       ↓
PARTIAL_CUTOVER
       ↓
NEW_AUTHORITATIVE
       ↓
ROLLBACK_WINDOW
       ↓
OLD_RETIRED
```

State transitions are the hard part of migrations. This machine exists to
prevent thinking of migration as `copy → flip switch → delete old`.

## Planning inputs

```text
source · destination · state owner · compatibility window
traffic transition · data transition · rollback boundary
validation · final cutover · old-system retirement
```

## Dual-state coexistence

Many migrations require old and new to live together:

```text
old authoritative
      ↓
dual compatible
      ↓
new receives shadow/read traffic
      ↓
new receives bounded authoritative traffic
      ↓
new authoritative
      ↓
old retained for rollback
      ↓
old retired
```

Do not destroy the old system at the exact moment authority changes unless
required.

## Data validation — more than row count

Depending on system: object count, checksums, semantic consistency,
referential integrity, timestamp ranges, sampled reads, read-after-write,
duplicate detection, missing records, ordering requirements.

## Mixed-state discipline

Assume partial progress at every step: partially migrated data, partially
updated schemas, both versions serving. Every phase must define what mixed
state is acceptable and how to detect it. Rollback boundary must be explicit:
after which transition is rollback no longer possible, and what forward
recovery replaces it?
