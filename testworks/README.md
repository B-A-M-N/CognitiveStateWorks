# TestWorks

A technology-agnostic, **single** `test_assurance` StateWork for CognitiveStateWorks.
It chooses meaningful tests, validates test evidence, maintains portfolio value,
and explicitly permits `NO_ADDITIONAL_TESTING_NEEDED`.

The package contains ten internal flows, a StateWork manifest, transition
contract, typed handoff schema, evidence kinds, examples, qualification cases,
and standalone static/decision-policy tests. The flow descriptors are documentation
and policy inputs, **not** independently registered StateWorks.

## Use
1. Establish the exact subject (revision + relevant mutable state + environment).
2. Triage changed behavior, risk and available evidence.
3. Choose a flow based on required decision. Advance StateWork via legal guards.
4. Preserve run receipts and mark omissions/risk. Qualify or explicitly decline
   additional work only when the stated scope is supported.
5. Reopen a completed claim when material facts change.

## Integration
See `../INSTALL.md` in the ZIP. The archive does not modify an existing
checkout or assert compatibility with uncommitted local extensions.
The reference qualification policy under `qualification/policy.py` is **not** a
replacement for the host's trusted runtime or external test runner.

## Invariants
- Do not mistake counts or green icons for meaningful coverage.
- Do not erase critical invariant coverage for throughput.
- Do not qualify a revision/environment other than the observed subject.
- Do not remove or rewrite tests without authorized controlled mutation.
- Do not claim qualification from an untrusted or missing receipt.
- Do not make direct StateWork-to-StateWork calls.
