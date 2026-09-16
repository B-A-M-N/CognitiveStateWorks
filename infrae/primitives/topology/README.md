# Primitive: Topology

The shape of the system: what exists, where it lives, how it is connected.

## What it captures

Nodes, services, networks, storage, control planes, data planes, and external
dependencies — with **placement**, since the same set of components arranged
differently has different failure and capacity behavior.

## Rules

- A topology model built from configuration alone is a hypothesis. Verify against effective runtime state (discovery is the flow that does this).
- Placement carries semantics: two replicas on one host, one rack, or one region are different systems.
- Record what a model was built from and when. Topology is a snapshot of evidence, not permanent truth.
- Vendor-neutral: the topology of a Kubernetes cluster, a systemd fleet, and a bare-metal stack are described with the same vocabulary — placement, connection, dependency, failure domain.
