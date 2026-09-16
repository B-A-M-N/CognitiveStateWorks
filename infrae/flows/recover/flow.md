---
flow: recover
operations: [recover, rollback, restore]
triggers: [recovery, recover]
states:
  from: [DEGRADED, INCIDENT, RECOVERING]
  through: [RECOVERING, STABLE]
framework_requirements: [owl, anchor, ward]
required_specialists: []
optional_specialists: []
---
# Flow: Recover (DEGRADED / INCIDENT → STABLE)

Use after: failed deployment, partial migration, host loss, data loss,
cluster corruption, network partition, secret compromise, configuration
drift, orchestration failure.

Goal:

> Recover authoritative state without compounding damage.

## Rules

1. Stop mutating. Reconstruct facts. Only then act. (Repository confusion
   compounds when mutation continues — so does infrastructure confusion.)
2. Re-observe effective state before each recovery step; the failure may have
   changed the topology your plan assumes.
3. Preserve recovery anchors before destructive steps: snapshots, backups,
   known-good configuration, out-of-band access. The only recovery path must
   not depend entirely on the infrastructure being recovered.

## Handles

- Rebuild node · restore database · reconstruct cluster · repair quorum ·
  restore backups · reissue credentials · reconcile state · drain backlog ·
  return redundancy.

## Quorum systems

Reason explicitly about member count, majority, partitions, stale members,
replacement procedure, leadership, split brain, loss of quorum. Do not
casually "fix" unavailable quorum systems by deleting membership state.

## Backup / restore / DR

Replication is not backup — replication reproduces deletes, corruption, and
malicious modifications. A backup is proven only by a tested restore.
Establish: what is backed up, frequency, storage location, independence from
the source failure domain, encryption, whether restore credentials survive
the disaster, tested restore time, data-loss window.

Where applicable state RPO (tolerable data loss) and RTO (tolerable recovery
time) — do not pretend these are known if they have never been measured. For
irreversible operations, define forward recovery instead of rollback.

## Completion condition

```text
service restored
+ state integrity verified
+ required redundancy restored
+ capacity restored
+ monitoring normal
```

not merely `HTTP 200 again`. "Service started" is not full recovery. Verify
with `../validate/` before declaring STABLE.
