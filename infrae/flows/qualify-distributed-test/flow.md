---
flow: qualify-distributed-test
states:
  through: [VERIFIED]
integrations:
  cognitiveframeworks:
    required: [owl, anchor]
required_specialists: []
optional_specialists: []
when:
  all:
  - field: operation
    in: [qualify, test, verify]
  - field: trigger
    in: [distributed_test, remote_test_host, cloud_lab, host_qualification]
  - field: current_state
    in: [OBSERVED, MODELED, ASSESSED, PLANNED, CHANGING, VERIFIED]
---
# Flow: Qualify a Distributed Test Environment

Use when work depends on a remote host, scheduled allocation, SSH session,
transferred source, or long-running remote test. Track whether the same
authorized host and exact source revision were tested, and whether the work
survived disconnection without being dispatched twice.

## Establish the target

Observe the allocation or remote environment before planning a connection.
Record its provider, project or owner, allocation identifier, lifecycle state,
valid time window, and the authoritative source of the active host identity.
If it is still scheduled, expired, or failed, mark the test blocked and keep
working only on independent preparation. A schedule time is not evidence that
the host is active. Never infer a hostname from an older allocation.

Connect only after the host name and host key are tied to an authorized source
such as the provider console, trusted inventory, or operator-provided pin. A
key scan discovers a key; it does not authenticate it. Keep connection details
scoped to the task and do not put credentials in logs or command history.

## Plan the run once

Before dispatch, record a unique run ID, repository, full target SHA, base SHA
when relevant, host identity, exact commands, working directories, expected
runtime, timeout, evidence destinations, and cleanup owner. Choose a unique
remote workspace and transfer only the revision-scoped source required by the
run. Verify the transfer hash, fetched commit, and checked-out `HEAD` before
building or testing. Do not use a moving branch name as source identity.

Bound concurrent jobs to the host's observed CPU, memory, disk, and runtime
capacity. Keep output attached to a durable log. When the operator needs a
visible terminal, keep that terminal showing the current run or a refreshing
log/status view; the display is useful feedback, while the saved log and job
state remain the record.

## Run and reconnect

Track every asynchronous dispatch by run ID, process or scheduler job ID,
command, start time, latest observed state, and log path. A tool call that
returns a session/job identifier means work was accepted, not that it finished.
Poll or wait on the same job within a bounded interval; keep working on
independent preparation while it runs, but do not start an equivalent run in
parallel unless the plan explicitly calls for concurrency.

If the terminal, SSH connection, or controller disconnects, first inspect the
existing job and host state using the recorded identifiers. Resume observation
of the existing job where possible. If its state cannot be established, mark
the result `INCONCLUSIVE` and reconcile before redispatch. Do not infer failure
from a quiet terminal or success from a stale progress message. Record both UTC
timestamps and the operator's local timezone when schedule timing matters.

## Evidence and completion

For each gate, retain the exact SHA, host identity and verified key source,
command, exit code, start/end timestamps, observed behavior, and sanitized log
path. Keep PASS, FAIL, BLOCKED, INCONCLUSIVE, and NOT_RUN distinct. Exit status
alone does not prove behavior, and a local fake does not prove a remote-host
property.

Mark the environment `VERIFIED` only for the specific gates whose required
observations are present and attributable to that host and source revision.
List unrun gates and external dependencies explicitly. A reconnect, controller
restart, or successful rerun does not erase an unexplained earlier failure.

## Handoff

Pass the receiving flow a run record containing allocation and host identity,
target SHA, job IDs, gate verdicts, evidence paths and hashes, resource limits,
and cleanup status. Use `../validate/` to assess test claims and `../recover/`
when the remote environment or its state needs repair.
