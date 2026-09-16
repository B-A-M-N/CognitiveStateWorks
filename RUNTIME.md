# StateWork Runtime Kernel

The tiny common kernel an **active** model carries while running any StateWork.
This is not the authoring protocol — when designing a StateWork, read
`PROTOCOL.md` in full. At runtime, hold only:

```text
current state
invariants
legal next transitions
guards
evidence
invalidation
```

## Kernel

1. **Current state.** What named state is the domain in right now, per the
   StateWork's own vocabulary.
2. **Invariants.** What must remain true across any transition for this task.
3. **Legal next transitions.** Only the edges the StateWork's state machine
   lists. Anything else is illegal by default.
4. **Guards.** Which conditions must hold before a transition may fire.
   Answered by evidence, not optimism.
5. **Evidence.** What observation proves the guard — at what strength. A
   successful command is construction evidence, not correctness evidence.
6. **Invalidation.** Which new observations would reopen the current state,
   and what the deterministic downgrade target is (see the owning StateWork).

## Handoff

When the domain changes, emit the StateWork's typed handoff packet
(`schemas/handoff-packet.schema.json`, freshness per the packet type). Do not
call another StateWork — route the packet through the composition layer.
