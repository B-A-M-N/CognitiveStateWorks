# Domain: Orchestration

Supplies orchestration and infrastructure-as-code analysis and actions to
Infrae flows. Does not own state transitions — an IaC specialist knows how to
run a plan/apply; whether the apply is a safe mutation is the Change flow's
call.

## Covers

Control plane vs data plane, management plane, scheduling behavior, IaC,
configuration drift, idempotence, immutable vs mutable infrastructure,
bootstrap dependencies, declarative reconciliation.

## Control plane vs data plane

Always distinguish:

```text
CONTROL PLANE — configures / schedules / coordinates
DATA PLANE    — performs actual workload
```

Ask: can the data plane continue when the control plane is temporarily
unavailable? Does control-plane failure stop new work only, or all work? Can
data-plane overload damage the control plane? Keep these failure domains
separate where practical.

## Management plane

Operational access (SSH, VPN, out-of-band management, cluster admin,
emergency console) is its own plane. Do not make the only recovery path
depend entirely on the infrastructure being recovered.

## IaC: declared ≠ effective

IaC provides reviewable intent, reproducibility, change history, drift
detection, repeatability. But `code exists ≠ runtime matches code`. Always
distinguish declared and effective state; a committed configuration does not
prove production matches it.

## Configuration drift

Drift sources: manual changes, emergency fixes, local overrides, outdated
nodes, partial rollout, version skew, unmanaged resources, configuration
caching. When drift exists, determine: is runtime authoritative? Is code
authoritative? Was the drift intentional? Will reconciliation destroy needed
state? **Do not blindly reapply desired state if production contains a
necessary emergency divergence. Understand first.**

## Idempotence

Infrastructure operations should converge safely when repeated. A good
operation must not accidentally duplicate users, firewall rules, routes,
resources, secrets, mounts, or registrations — retry safety matters because
infrastructure operations fail partially.

## Immutable vs mutable

Prefer immutable replacement where it improves reproducibility, rollback, and
drift resistance. Use mutable systems when stateful or operational constraints
make them appropriate. Do not adopt immutability as dogma.

## Bootstrap dependencies

Look for circular startup chains:

```text
service A requires DNS
DNS requires database
database credential requires vault
vault startup requires service A
```

Every critical stack needs a comprehensible bootstrap chain, and at least one
recovery path that does not run through the stack being recovered.
