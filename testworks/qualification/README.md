# Qualification contract

The included scenario suite demonstrates opposing outcomes: meaningful tests
are requested when distinct risk is uncovered; no additional testing is requested
when subject-matched evidence is already adequate. It also rejects stale
receipts, untrusted results, and unsafe deletion.

`policy.py` is a *reference decision model for scenario tests only*. It is not
loaded by the CognitiveStateWorks trusted host, not an executor, and not an
authorization mechanism. Host integration must independently validate:

1. **Subject identity:** current revision, uncommitted changes, test definitions,
   environment/runner, dependencies and task-relevant workload.
2. **Run receipts:** issuer authenticity, artifacts and commands, status, timestamps,
   results and fingerprint match.
3. **Coverage/sufficiency:** required risk/critical invariants and meaningful
   detection guarantees, not test counts or arbitrary scoring.
4. **No additional testing:** credible rationale, fresh pre-existing evidence,
   explicit omitted tests, and the limited decision scope.
5. **Portfolio mutation:** owner approval, preserved fault detection and rollback;
   pass only a proposal to repository-mutation authority.
6. **Invalidation:** changed subject, contradiction, newly observed failures or
   changed release requirement reopens evidence deterministically.

`python3 -m unittest discover -s testworks/tests -v` checks the reference rules,
manifest/transition integrity and the sample packet. It cannot establish that
a real host has wired and enforced these guards.
