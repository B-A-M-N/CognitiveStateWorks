# Internal flow router

These are ten *internal flows* of TestWorks. They are not separately registered
StateWorks and have no independent transition authority. Choose exactly one
based on intended output; if several apply, complete the earliest unanswered
precondition, then explicitly transition before selecting the next.

| Need | Flow |
| --- | --- |
| What changed and what is already covered? | triage |
| Which behavior/oracle should be protected? | design |
| Build or specify effective cases | generate |
| Which existing suites should run (or none)? | select |
| Obtain reproducible run receipts | execute |
| Explain a failure, skip or flake | diagnose |
| Which tests still have value? | audit |
| Can duplication be safely removed? | consolidate |
| Is the subject qualified? | qualify |
| A past conclusion became stale | recover |

Avoid creating new tests unless design establishes a gap; avoid broad execution
unless selection establishes need. Do not use an internal flow as a bypass
around the transition guards in `../transitions.yaml`.
