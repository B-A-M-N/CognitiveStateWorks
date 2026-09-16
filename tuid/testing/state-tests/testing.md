# Testing: State Transition Tests

Layer 1 — the deterministic base. Test pure or mostly pure application
behavior:

```text
Given: selection = 2
When:  MoveNext
Then:  selection = 3
```

Fast, deterministic, many. Cover: state transitions per interaction intent,
focus transitions, overlay stack changes, selection/scroll validity, stale-result
guards, cancellation. These tests prove interaction **semantics** — they say
nothing about rendering; that is layout/snapshot territory.
