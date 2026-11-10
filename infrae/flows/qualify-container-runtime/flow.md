---
flow: qualify-container-runtime
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
    in: [docker_runtime, container_lifecycle, sandbox_runtime, container_host_qualification]
  - field: current_state
    in: [OBSERVED, MODELED, ASSESSED, PLANNED, CHANGING, VERIFIED]
---
# Flow: Qualify a Container Runtime

Use when a qualification depends on Docker or another container runtime's
effective host behavior. A passing API operation is not by itself proof of
container isolation, process attribution, lifecycle transitions, or recovery.

## Capture the baseline and isolate the run

Record the host, kernel, runtime and version, active context/socket, runtime
configuration, resource headroom, existing containers, images, networks,
volumes, and relevant firewall state before changing anything. Distinguish
pre-existing, shared, task-owned, and host-global resources. If ownership or
the target daemon is unclear, stop before mutation.

Give the run a unique project/namespace, image tag, network and resource names.
Check ports, subnets, names, and capacity for collisions before startup. Build
from the verified checkout and record the source SHA, build command, image ID,
and available revision labels. A mutable tag, branch name, requested label, or
successful build command alone does not prove which image a running container
uses.

Use the repository's deployment entry point when it owns credential creation,
migrations, network validation, or readiness checks. Before testing, verify
effective runtime identity, health/readiness, network attachment, mounts,
and the actual image ID of every container in the tested stack.

## Measure behavior at the claimed boundary

Define each gate's runtime, operation boundary, baseline, expected behavior,
and required evidence before execution. Attribute process counts to the
specific client, host process, container, and time window. Include overlapping
polling and background work in the record; if the measurement window differs
from a published baseline, report the numbers without claiming comparability.

Test positive and negative controls for network or isolation claims. A timeout
or silent drop is inconclusive unless the intended enforcement point is shown
to have handled the traffic. Keep before/after counters, packet observations,
container/runtime metadata, and client-visible results aligned to one run.

## Verify retained-container lifecycle

Treat the application operation and the Docker lifecycle as separate gates.
After an inactivity/idle-stop test, inspect the exact container ID and state;
then verify stop, restore, identity preservation, and a subsequent live
operation as separate observations. Do not substitute a successful job result
for proof that the container stopped. If a stop assertion fails, preserve the
first failure, inspect runtime state, events, health, configured timeout and
manager logs, and classify whether the cause is product, host, harness,
configuration, evidence gap, or unknown. Fix the cause or mark the gate
inconclusive before another run. Do not repeat a long smoke test blindly.

Check cleanup against the resource ledger by exact IDs. Remove only resources
created by this run. Never delete by name prefix, stop a shared daemon, or
change unrelated firewall policy because the baseline looked empty. Record
host-global changes and residuals; a restored test stack does not imply the
host returned to baseline.

## Evidence and completion

For each gate, retain target SHA, host/runtime identity, exact image IDs,
commands, timestamps, exit status, observed lifecycle state, process/counter
measurements, and sanitized evidence paths. PASS requires the behavior and
attribution appropriate to the claim. Keep FAIL, BLOCKED, INCONCLUSIVE, and
NOT_RUN distinct, and preserve partial evidence.

Mark `VERIFIED` only for the runtime and test envelope actually observed.
Report untested runtimes and missing host capabilities as blockers or NOT_RUN;
do not generalize Docker results to Kata or a local fake to a real host.

## Handoff

Pass the receiving flow the baseline, revision and image provenance, per-gate
observations, exact resource ledger, cleanup result, and residual host changes.
Use `../validate/` to assess the qualification claim and `../recover/` for
runtime or host failures.
