# CognitiveStateWorks

> **Explicit, evidence-backed workflow state for AI agents.**

## What problem does this solve?

Agent failures are not always behavioral. An agent can behave carefully and still
mutate a repository before establishing its state, treat a successful deployment
as proof of infrastructure health, declare a UI fixed without exercising the
defect, or jump straight from activity to completion.

Those are **state-model failures**, not merely reasoning failures. The agent needs
to know not just how to behave, but what state the work is in and what is valid
from here.

## What does it actually do?

CognitiveStateWorks gives AI agents an explicit, evidence-backed model of the work
they are performing. It records the current state of a task or operational
subject, defines which transitions are permitted, and identifies the evidence
required to proceed.

For example, an agent should not treat infrastructure as verified merely because a
deployment command succeeded. CSW requires the appropriate validation evidence
before accepting that state transition.

Workflow state persists independently of the agent's conversation, and new
observations can invalidate earlier conclusions.

```text
UNKNOWN
   │ Trusted discovery evidence
   ▼
OBSERVED
   │ Authorized plan
   ▼
PLANNED
   │ Authorized execution
   ▼
CHANGING
   │ Required verification evidence
   ▼
VERIFIED
   │ New contradicting observation
   ▼
DEGRADED
```

*This chain is illustrative. It is not a literal definition of Infrae's entire
transition graph.*

## What does it not do?

- CSW does **not** prescribe how an agent should reason. That belongs to
  CognitiveFrameWorks.
- CSW does **not** evaluate behavioral tendencies or decide whether an
  intervention helped. That belongs to DigitalPsychology.
- CSW is a domain-state runtime, not a general database or policy language.

## Advisory versus enforcing installation

CSW ships two importantly different installation experiences. **Read this before
installing** — installing the guidance package does *not* create hard workflow
enforcement.

| Installation | What you get |
| --- | --- |
| **Advisory** | Workflow instructions and guidance available to the agent. Transitions are **not** independently enforced. |
| **Enforcing** | Runtime state authority, evidence checks, and transition validation through trusted-host interfaces. |

Use the advisory product for documentation and workflow guidance:

```bash
python3 scripts/install-stateworks.py --registry example-host="$HOME/.example/skills"
```

Use the enforcing product for standalone state authority:

```bash
python3 scripts/install-stateworks.py \
  --registry example-host="$HOME/.example/skills" \
  --enforcing-runtime
```

## How can I use it independently?

CSW can own state and evidence without CFW or DP. From this repository, run the
enforcing runtime example:

```bash
python3 scripts/quickstart-standalone.py
```

Expected output:

```text
initial: UNKNOWN revision 1
transition without evidence allowed: False
transition with trusted evidence allowed: True
after restart: OBSERVED revision 2
```

The example uses the Infrae transition contract, initializes a subject through
`StandaloneHostInterface`, rejects a transition without host-attested discovery
evidence, and proves that state survives a new interface instance.

## The included StateWorks

| StateWork | Purpose                                             |
| --------- | --------------------------------------------------- |
| **Gitter** | Repository inspection and state establishment       |
| **Getter** | Controlled repository modification and recovery     |
| **Infrae** | Infrastructure operations, validation, and recovery |
| **tui'd** | Terminal interface design and development workflows |

Each is a **registered workflow bundle with its own contracts** — not an
autonomous agent, and not a dynamically spawned specialist. Registration means the
StateWork is available to CSW's resolver; it does not mean it is loaded into every
agent. CSW resolves eligibility and composition compatibility, and the trusted host
or DP chooses among the returned legal candidates. See
[`docs/architecture.md`](docs/architecture.md).

## How does it integrate with the other two?

| Deployment | CSW role | Other-system requirement |
| --- | --- | --- |
| **CSW alone** | Workflow selection, durable subject state, evidence, and legal transitions | None |
| **CFW alone** | Not loaded | CFW resolves components and action enforcement independently |
| **CSW + DP** | Authoritative workflow state, eligibility, evidence, and transition enforcement | DP may request an eligible StateWork through the private host control bridge |
| **CFW + DP** | Not loaded | DP can adapt without CSW; CFW independently enforces any separately enabled action gates |
| **CFW + CSW** | Authoritative workflow state and evidence | CFW supplies task components and action guards; DP is not required |
| **CFW + CSW + DP** | Authoritative workflow state, candidate eligibility, and transition enforcement | DP coordinates behavioral interventions; CFW supplies signals and validates component directives |

When DP is enabled, it may request activation only from CSW's eligible choices; CSW
validates and commits the selection. DP cannot create eligibility, weaken a
transition contract, or rewrite workflow state. CFW consumes normalized workflow
requirements through its host port and keeps its component and action gates local.

## What has been demonstrated, and what remains experimental?

Demonstrated: registry integrity, transition legality, evidence provenance,
durable state, restart recovery, and concurrent revision safety, plus integration
with the CFW `StateAuthority` port and one recorded Codex adapter fixture
(10/10 CFW+CSW trials, 4/4 criteria).

Not established: general efficacy. The current CFW task benchmark does not
establish improvement from the full system; that requires host-verified baseline,
CFW, CFW+CSW, CFW+CSW+DP, and CFW+CSW+DP+Laya cohorts on the same task
distribution. See [`docs/validation.md`](docs/validation.md).

## Where is the technical documentation?

| Document                                                        | Responsibility                                                    |
| --------------------------------------------------------------- | ----------------------------------------------------------------- |
| [`docs/architecture.md`](docs/architecture.md)                  | Persistence, revisions, authority, evidence, workflow selection    |
| [`docs/integrations.md`](docs/integrations.md)                  | Standalone, CFW, DP, host interfaces                              |
| [`docs/validation.md`](docs/validation.md)                      | Validators, concurrency, recovery, installation checks            |
| [`PROTOCOL.md`](PROTOCOL.md)                                    | Authoring requirements for StateWorks (unchanged)                 |
| [`RUNTIME.md`](RUNTIME.md)                                      | Compact runtime-facing state contract (unchanged)                 |
| [`docs/triad-overview.md`](docs/triad-overview.md) | How the three authorities fit together |

## Support and limits

Linux is the supported platform; the repository does not claim Windows support.
CSW is a domain-state runtime, not a general database or policy language. Trusted
hosts must provide evidence validators and deployment-specific freshness context.
The automated three-project release gate is in the sibling CFW repository.

## License and contribution

These projects are released under the [MIT License](LICENSE). Contributions are
welcome through repository issues and pull requests. Please include a focused
regression or acceptance check for behavior changes, keep authority boundaries
explicit, and do not claim model-performance improvements without the
corresponding qualification evidence.

## FreeInference Acknowledgment

This project was developed with the assistance of AI inference provided by [FreeInference.org](https://freeinference.org/).

This is an independent project. FreeInference did not review, sponsor, direct, supervise, approve, or endorse its development or contents. The project's design, implementation, claims, and maintenance are independent of FreeInference.

If you find this project useful, please consider supporting the infrastructure that helped make its development possible by donating to [FreeInference.org](https://freeinference.org/).
