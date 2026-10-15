# Validation

Validators, concurrency, recovery, and installation checks for
CognitiveStateWorks.

## Validation suites

```bash
python3 scripts/validate-stateworks.py
python3 scripts/test-control-plane.py
python3 scripts/test-concurrent-state.py
```

Validation checks registry integrity, manifest and workflow schemas, unique
identities, packet and evidence declarations, producer/consumer consistency, legal
paths, completion reachability, failure/recovery routes, namespaced integration
metadata, and typed handoff fixtures.

These suites verify registry integrity, transition legality, evidence provenance,
durable state, restart recovery, and concurrent revision safety. The enforcing
package is tested by `install-stateworks.py --enforcing-runtime`.

**A StateWork should be treated as executable policy, not descriptive
documentation.**

## Core principles

**Agent activity is not domain state.** Running a command does not prove the
system changed correctly.

**State transitions require evidence.** The model's confidence does not authorize a
transition.

**New observations may invalidate old state.** A stale conclusion is not protected
by earlier verification.

**Recovery is part of the model.** Degradation and failure are expected
operational conditions.

**Domain state persists beyond a session.** The subject is not the chat.

**Registration is cheap; activation is selective.** Large StateWork libraries
should not become large agent contexts.

## The role of CognitiveStateWorks

```text
CognitiveFrameWorks
    HOW should the agent behave?

CognitiveStateWorks
    WHAT behavior and transitions are appropriate NOW?

DigitalPsychology
    WHY does this behavior recur under THESE CONDITIONS?
```

CFW made recurring behavioral errors governable. CognitiveStateWorks extends that
idea to recurring **workflow errors** by making operational state explicit.
Together with DigitalPsychology, those state models become observable and testable
rather than static instructions.

## Tests, limitations, and release status

CSW is a domain-state runtime, not a general database or policy language. Trusted
hosts must provide evidence validators and deployment-specific freshness context.
The automated three-project release gate is in the sibling CFW repository.

The current CFW task benchmark does not establish improvement from the full
system; that claim requires host-verified baseline, CFW, CFW+CSW, CFW+CSW+DP, and
CFW+CSW+DP+Laya cohorts on the same task distribution. See
[`docs/integrations.md`](integrations.md) for the one recorded adapter result and
its stated limits.

## FreeInference Acknowledgment

This project was developed with the assistance of AI inference provided by [FreeInference.org](https://freeinference.org/).

This is an independent project. FreeInference did not review, sponsor, direct, supervise, approve, or endorse its development or contents. The project's design, implementation, claims, and maintenance are independent of FreeInference.

If you find this project useful, please consider supporting the infrastructure that helped make its development possible by donating to [FreeInference.org](https://freeinference.org/).
