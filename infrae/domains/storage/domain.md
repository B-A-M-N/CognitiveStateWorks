# Domain: Storage

Supplies storage analysis and actions to Infrae flows. Does not own state
transitions — a backup specialist knows how to run a restore; whether
recovery is complete is the Recover flow's call, verified against its
completion condition.

## Covers

Local disks, block storage, object storage, shared filesystems, persistent
volumes, databases, replication, snapshots, backup, restore, durability,
write ordering, storage pressure, IOPS, throughput, latency, filesystems.

## Key discipline

**A disk can be technically non-full and still be operationally saturated.**
Monitor free capacity, inode exhaustion, write latency, fsync latency, IOPS,
throughput, queue depth, compaction, WAL growth, snapshot growth, and
temporary-space requirements.

## Stateful systems

Stateful infrastructure requires stronger reasoning. Identify: source of
truth, writers, readers, replication model, consistency model, ownership,
durability guarantee, backup, restore, migration model, failure behavior.
Never assume state can be recreated merely because the application binary
can.

## Source of truth

For every critical datum, determine one authoritative ownership model.
Ambiguous ownership causes split brain, lost writes, stale reads, and
reconciliation ambiguity. If several systems may modify the same state,
arbitration must be explicit.

## Replication vs backup

Replication is not backup — replication faithfully reproduces accidental
deletes, corruption, and malicious modifications. They solve different
problems; resilient systems need both, with backups independent of the
source failure domain.

## Backup and restore

A backup is proven only by a tested restore. Establish: what is backed up,
frequency, storage location, independence from source failure domain,
encryption, whether restore credentials survive the disaster, measured
restore time, and the data-loss window. Where applicable, RPO and RTO must be
measured, not asserted.

## Write ordering and durability

Determine what durability the workload actually requires (fsync behavior,
replication acknowledgment semantics) and what the storage layer actually
provides under power loss, crash, and partial write. Snapshot consistency
semantics matter for databases — a crash-consistent snapshot and an
application-consistent one are different artifacts with different recovery
properties.
