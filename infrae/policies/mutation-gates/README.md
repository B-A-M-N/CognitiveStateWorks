# Policy: Mutation Gates

Hard gates that bind all Infrae flows. No flow may weaken them.

## The Change Gate

Before production-impacting mutation, answer:

```text
1.  What exact invariant must remain true?
2.  What component actually owns this state?
3.  What are the dependencies?
4.  What is the blast radius?
5.  What failure domains are involved?
6.  How will success be observed?
7.  How will partial success be detected?
8.  What happens if this operation stops halfway?
9.  What is rollback?
10. Can rollback itself fail?
11. Does rollback require old state that this change destroys?
12. Is the system still compatible with the previous version?
13. What resource headroom exists during transition?
14. What happens to in-flight work?
15. What happens to queued work?
16. What happens to persistent state?
17. What happens to authentication/authorization?
18. What condition causes the operator to stop or abort?
```

If critical answers are unknown, investigate before mutation. The gate runs
**before** execution, not after — and not from memory of a similar change.

## Failure Injection Gate

Before failure testing production-like systems:

```text
scope · expected behavior · abort condition · monitoring · recovery
· affected users · ownership
```

Do not perform uncontrolled destructive experiments on critical
infrastructure. The objective is validating claimed resilience, not chaos.

## Decommission gate

The Decommission flow's checklist is a gate: unknown consumers → BLOCKED,
not "proceed carefully."

## Gate authority

Gates are answered by evidence about effective state. "The command looks
easy" and "it worked in dev" do not satisfy a gate. Risk classification
(HIGH/CRITICAL) strengthens the evidence a gate demands; it never waives it.
CRITICAL findings (deleting production state, replacing trust roots, global
routing, destructive migration) do not pass — isolate or recover first.
