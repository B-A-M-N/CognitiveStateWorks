# Integrations

Standalone, CFW, DP, and host interfaces for CognitiveStateWorks.

## Standalone

CSW can own state and evidence without CFW or DP. From this repository:

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
Repository-truth transitions remain bound to their specialized validator.

For a deployable enforcing installation:

```bash
python3 scripts/install-stateworks.py \
  --registry demo="$HOME/.demo-csw" \
  --enforcing-runtime
```

That product contains the controller, schemas, compiled StateWork bundles, flows,
and validators declared by the runtime package. The ordinary installation remains
an advisory skill product.

## CSW is host-neutral

CSW's workflow authority consumes normalized workflow requests, state snapshots,
and evidence references. It does not depend on a model or harness event protocol;
a host adapter translates those events before calling CSW. Eligibility, state,
evidence, and transition decisions therefore stay the same across harnesses.

The trusted host/runtime owns task lifecycle orchestration and event
normalization. DP may request activation only from CSW's eligible choices; CSW
validates and commits the selection. CFW consumes normalized workflow requirements
through its host port and keeps its component and action gates local. CSW is not
the universal StateWork selector.

## Optional integrations

- **CSW alone:** use `StandaloneHostInterface` and the enforcing installation; CFW
  and DP are not required.
- **CSW + CFW:** CFW supplies task components and action enforcement; CSW retains
  workflow selection, state, evidence, and transition authority.
- **CSW + DP:** DP may rank and request activation of an eligible StateWork. CSW
  checks the composition and selection revision, then records the active set; DP
  cannot create eligibility, weaken a transition contract, or rewrite workflow
  state.
- **CSW + CFW + DP:** CFW supplies cognitive components and action enforcement, DP
  coordinates behavior through explicit ports, and CSW remains the authority for
  workflow selection, state, evidence, and legal transitions.

| Deployment | CSW role | Other-system requirement |
| --- | --- | --- |
| **CSW alone** | Workflow selection, durable subject state, evidence, and legal transitions | None |
| **CFW alone** | Not loaded | CFW resolves components and action enforcement independently |
| **CSW + DP** | Authoritative workflow state, eligibility, evidence, and transition enforcement | DP may request an eligible StateWork through the private host control bridge |
| **CFW + DP** | Not loaded | DP can adapt without CSW; CFW independently enforces any separately enabled action gates |
| **CFW + CSW** | Authoritative workflow state and evidence | CFW supplies task components and action guards; DP is not required |
| **CFW + CSW + DP** | Authoritative workflow state, candidate eligibility, and transition enforcement | DP coordinates behavioral interventions; CFW supplies signals and validates component directives |

CSW's standalone runtime and its CFW integration remain usable without DP. The
complete three-system deployment adds adaptation while preserving CSW as the only
authority that can activate eligible StateWorks or commit legal workflow
transitions.

## How CFW discovers CSW

CFW discovers this integration through the optional
`cognitiveframeworks.statework_providers` Python entry point included in the CSW
package. Installing CSW does not require CFW; CFW-only deployments use an empty
provider and do not import CSW. When requested by CFW, this provider constructs
CSW's `CFWAuthorityAdapter` for CFW's neutral `StateAuthority` port; workflow
storage, evidence handling, scope binding, and legal transitions remain
implemented here.

## Authority identity and revision checks

The host verifies that CFW and DP adapters refer to the same stable CSW authority
identity, including the registry, storage, workflow scope, and contract pin.
Selection changes use expected-revision compare-and-swap. A host can checkpoint
the exact selection before a DP control tick, restore it after an aborted
transaction if the revision still matches, or finalize the checkpoint after
commit.

## The behavioral snapshot

The host calls `WorkflowAuthority.behavioral_snapshot(...)` with the workflow
scope and an optional bounded candidate list. It does not supply active workflow
identities: CSW reads those from its own revisioned selection store.

The snapshot returns current authoritative workflow states, the last
evidence-supported `previous_state` and `progress_class` when recorded, and
`legal_next_states` derived from currently eligible transitions. A legal next state
still requires the transition's declared evidence when the host applies it. The
snapshot also returns only registered, composition-compatible StateWorks with
bounded `behavior_tags`. DP may rank those candidates; tags are descriptive hints
and do not grant activation or transition authority.

Activation uses `WorkflowAuthority.activate_workflow(...)` with a contract hash and
expected selection revision. Independent host activations are permanent unless the
host explicitly releases them. A DP activation must include its control-session and
intervention IDs plus an action-index expiry; only that matching DP owner can
release it. CSW expires due DP leases during a behavioral snapshot when the host
supplies the current action index, while preserving composition-required
dependencies and independently owned selections. Applying any workflow step still
uses `WorkflowAuthority.apply_step(...)` with evidence and an expected workflow
revision.

When the final direct lease on a prerequisite is released while active dependents
still require it, CSW retains the prerequisite as a dependency-owned selection and
reports a typed `retained` disposition. It releases that selection after the last
dependent closes. Snapshot freshness is checked from the persisted workflow
`updated_at` value, including after restart, and selection updates remain
revision-checked under concurrent writers.

In the three-system runtime, DP receives a CSW snapshot containing the current
selection revision, active workflow states, legal steps, and only registered,
composition-compatible candidates. DP may request one eligible activation or
release a temporary selection when its bounded intervention ends. CSW checks the
expected selection revision for either operation and returns the new authoritative
snapshot. DP cannot infer eligibility from tags or claim that a requested
StateWork became active without CSW confirmation.

## Host binding for DP without CFW

For a DP host that does not use CFW to discover workflows, CSW provides
`cognitive_statework.host_binding.resolve_bindings(authority, runtime_identity,
task_context)`. It returns immutable contract pins for the scope's active
workflows and the registered candidates CSW says are currently
composition-compatible. The host passes them to DP's structural adapter:

```python
from cognitive_statework.host_binding import resolve_bindings
from digital_psychology.runtime.adapters import CSWRuntimeAdapter

workflow_bindings = resolve_bindings(
    csw_authority, runtime_identity, {"domains": task_domains})
csw_port = CSWRuntimeAdapter(
    csw_authority,
    identity=runtime_identity,
    bindings={item.identity["statework_id"]: item
              for item in workflow_bindings},
)
```

The resolver imports no CFW or DP code. It gets registered entries and composition
decisions from CSW, binds each result to the exact runtime scope, and rejects
unknown IDs or task-context attempts to replace that scope.

## Codex adapter integration evidence

This is evidence for one optional harness adapter. CSW's workflow contracts and
authority remain host-neutral and do not require Codex.

The Codex App Server adapter matrix recorded 10/10 CFW+CSW trials at 4/4
criteria, with 10/10 completion permits. The run used one coding fixture,
`deepseek-v4-flash`, and the FreeInference external-provider Responses route;
ChatGPT-mode attempts had stopped at workspace-routing discovery before the host
or model turn began. This dirty-tree result establishes integration and
non-regression for that fixture. **It does not establish general efficacy.** See
the [CFW live-results index](https://github.com/B-A-M-N/CognitiveFrameWorks/blob/master/evaluation_fixtures/live-results/README.md)
for the run record and its limitations.

## FreeInference Acknowledgment

This project was developed with the assistance of AI inference provided by [FreeInference.org](https://freeinference.org/).

This is an independent project. FreeInference did not review, sponsor, direct, supervise, approve, or endorse its development or contents. The project's design, implementation, claims, and maintenance are independent of FreeInference.

If you find this project useful, please consider supporting the infrastructure that helped make its development possible by donating to [FreeInference.org](https://freeinference.org/).
