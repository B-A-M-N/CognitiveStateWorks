---
flow: model
required_specialists: []
optional_specialists: []
---
# Flow: Model (OBSERVED → MODELED)

Purpose: turn observations into a system model. This is one of the most
important flows — most infrastructure failures hide in modeling errors.

## Build six graphs from the observation packet

```text
observations
    ↓
topology graph
  + dependency graph
  + state-ownership graph
  + trust graph
  + failure-domain graph
  + resource graph
```

## Detect state disagreement

Explicitly compare declared / observed / effective state:

```text
declared replicas = 4
runtime replicas  = 4
healthy replicas  = 2
serving replicas  = 1
```

Those are not one state. Record every disagreement as a finding.

## Dependency edges carry behavior

For each important edge ask:

```text
What does A assume about B?
How does A detect B failure?
How long before A reacts?
Does A retry? Where does retry traffic go?
Can failure cascade backward?
Can stale state persist?
Who owns recovery?
```

A dependency is not an arrow; it includes behavior under failure.

## Hidden dependency detection

Look for coupling through: shared database, filesystem, cache, credentials,
DNS, queue, port, kernel resources, rate limits, API quota, control plane,
service account, NAT gateway, network path, persistent volume, scheduler, GPU
memory, host memory, environment variables, secrets, implicit startup
ordering. Two services may appear independent while sharing a critical
resource.

## Failure domains

Evaluate redundancy against failure domains: process, container, VM, host,
rack, switch, power circuit, AZ, region, provider, control plane, identity
provider, DNS provider, storage backend, database cluster, network path,
configuration source, deployment pipeline, human operator.

> What single event can remove multiple supposedly redundant components?
> That event defines a shared failure domain.

3 replicas on one machine = process redundancy only. 3 replicas on 3 machines
sharing one database = database SPOF intact.

## Single points of failure

Search explicitly for: one database, proxy, gateway, secret store, DNS
provider, control node, scheduler, uplink, storage controller, credential,
operator machine, deployment mechanism. Not every SPOF must be removed — but
important SPOFs must be **known**.

## Bootstrap dependencies

Look for circular startup chains (service needs DNS, DNS needs database,
database credential needs vault, vault startup needs the service). Every
critical stack needs a comprehensible bootstrap chain, and the only recovery
path must not depend entirely on the infrastructure being recovered.
