# Aspect: Feedback States

Every data-bearing component should consider:

```text
INITIAL · LOADING · READY · EMPTY · STALE · DEGRADED · ERROR · DISCONNECTED
```

Avoid showing a blank rectangle for five semantically different states.

## Loading

Communicate useful state: `Loading configuration…`, `Connecting to node…`,
`Indexing 4,251 files…`. Avoid animations that provide motion but no
information.

## Empty — differentiate

```text
nothing exists
filter matched nothing
data failed to load
```

Those imply different user actions. Blank-on-empty hides which one applies.

## Errors

An error should answer, where feasible: what happened? what was affected? is
my state safe? what can I do? can I retry? where can I inspect details?
Avoid generic `Something went wrong` when the application has actionable
context. Usable error text is an accessibility consideration.
