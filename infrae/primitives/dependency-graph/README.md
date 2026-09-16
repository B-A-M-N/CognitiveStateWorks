# Primitive: Dependency Graph

The system's dependency structure including behavior under failure.

## What it captures

For each edge A → B:

```text
What does A assume about B?
How does A detect B failure?
How long before A reacts?
Does A retry? Where does retry traffic go?
Can failure cascade backward?
Can stale state persist?
Who owns recovery?
```

A dependency is not an arrow; it includes **behavior under failure**.

## Hidden dependencies

Coupling hides in shared: database, filesystem, cache, credentials, DNS,
queue, port, kernel resources, rate limits, API quota, control plane, service
account, NAT gateway, network path, persistent volume, scheduler, GPU memory,
host memory, environment variables, secrets, implicit startup ordering.

Two services may appear independent while sharing a critical resource.
`Git says clean` has a parallel here: *no textual dependency ≠ no semantic
dependency*.

## Edge classification

- **Hard dependency** — A fails when B fails.
- **Soft/degradable** — A degrades but survives B's failure.
- **Startup dependency** — A cannot boot without B; may not need B afterward.
- **Operational dependency** — A cannot be deployed/recovered without B (deploy pipeline needs the registry it deploys).

Operational dependencies are the ones most often missed and most dangerous
during recovery.

## Bootstrap chains

Look for circular startup dependencies. Every critical stack needs a
comprehensible bootstrap chain, and recovery must not depend entirely on the
infrastructure being recovered.

## In IaC

IaC dependency graphs describe *intent*. Runtime dependency graphs describe
reality. The Model flow builds both and diffs them.
