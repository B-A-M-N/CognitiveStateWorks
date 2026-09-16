# Primitive: Failure Domain

The set of components a single event can remove.

## Catalog

```text
process · container · VM · host · rack · switch · power circuit
availability zone · region · provider · control plane · identity provider
DNS provider · storage backend · database cluster · network path
configuration source · deployment pipeline · human operator
```

## The defining question

```text
What single event can remove multiple supposedly redundant components?
```

That event defines a shared failure domain. Two replicas on the same host are
not host-failure redundancy. Three services using the same datastore are not
independent. Two regions behind one global control plane may not be
region-independent.

## The redundancy test

```text
replica count
+ failure-domain separation
+ state independence
+ routing behavior
+ health detection
+ failover behavior
+ capacity after failure
```

- 3 replicas on one machine → process redundancy only.
- 3 replicas on 3 machines sharing one database → database SPOF intact.
- Post-failure capacity matters: N−1 surviving capacity is part of the redundancy claim, not an afterthought.

## SPOF inventory

Search explicitly for: one database, proxy, gateway, secret store, DNS
provider, control node, scheduler, uplink, storage controller, credential,
operator machine, deployment mechanism. Not every SPOF must be removed — but
important SPOFs must be **known**, with residual risk stated in the Evidence
Packet.

## Failure testing relationship

A failure domain that has never had a failure injected into it is a claim,
not a property. Failure testing (Reliability domain, gated by
`policies/destructive-change/`) is how failure-domain claims become evidence.
