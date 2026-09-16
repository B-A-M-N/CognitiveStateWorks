---
name: getter
description: >
  Risk-gated discipline for actually changing Git repository state — merging,
  rebasing, squashing, cherry-picking, reverting, resolving conflicts, testing
  branch integration, force-pushing, and recovering from a repository that has
  gone wrong. Trigger whenever a mutation is being considered or performed:
  merge, rebase, squash, reset, revert, cherry-pick, force push, detached HEAD,
  conflict resolution, combining or collapsing commits, testing several
  branches together, or repository recovery after something was overwritten,
  lost, or rewritten by mistake. Also trigger the moment a destructive
  operation is even being contemplated, since the gate in this skill must run
  before — not after — execution. Companion skill `gitter`
  handles observing and establishing repository state beforehand; use it
  first (or trust its handoff packet) to establish ownership, divergence, and
  isolation before anything here executes. This skill owns MUTATE, VERIFY,
  and REPORT/RECOVER.
---

# Getter — Git Mutation & Recovery Discipline

> **StateWork note.** Getter is the mutation half of a Repository StateWork,
> implementing `../PROTOCOL.md` implicitly: risk classes and the Mutation
> Gate are its transition guards (elements 5–6), STOP-then-reconstruct is its
> invalidation/recovery layer (elements 9, 11), and the Evidence Packet is
> its handoff contract (element 13). Observation-phase work belongs to the
> companion skill `gitter`.

## Purpose

This skill governs **actually changing repository state safely** — and
recovering when a change went wrong.

Its job is to ensure that every mutation:

* is preceded by an explicit gate, not habit
* is classified by risk before it runs
* preserves a path back if it's wrong
* is verified against the *resulting* state, not just its exit code
* is reported so another engineer could reconstruct what happened

It assumes repository truth has already been established — normally by the
companion skill `gitter`, whose Truth Packet and Standard
Assessment feed directly into the Mutation Gate below. If no such packet
exists and state is unknown, stop and establish it first; this skill should
never be the first thing that touches an unfamiliar repository.

Freshness is part of the packet, not a side channel. The Truth Packet carries
`observed_at`, repo identity, observed HEAD, working-tree fingerprint,
active-worktree snapshot, remote-state fingerprint where relevant, schema
version, and explicit invalidation conditions
(`schemas/repository-truth-packet.schema.json`). Before mutating, run the
freshness gate:

```text
Is the truth packet still valid?
  yes → proceed
  no → request or re-run only the invalidated observations
```

"Do not blindly rerun the entire observation system." If the packet is stale,
only the invalidated observations are re-established; the rest is trusted
until a condition invalidates it.

---

## Core Doctrine

> A command having executed successfully does not prove the resulting state
> is correct.

None of the following prove correctness:

* a successful rebase (does not prove behavioral preservation)
* a successful merge (does not prove semantic independence)
* a successful push (does not prove the correct branch, or correct SHA,
  landed on the remote)
* disappearing conflict markers (does not prove a conflict was resolved
  *correctly* — only that it compiled)

Every mutation in this skill follows:

```text
(truth established by gitter)
        ↓
CLASSIFY RISK
        ↓
MUTATE
        ↓
VERIFY
        ↓
REPORT  (or, if something went wrong: RECOVER)
```

Never collapse this into `MUTATE → assume success`.

---

## Scope

This skill owns:

* rebases, merges, squashes, cherry-picks, reverts
* conflict resolution, including semantic (not just textual) conflicts
* branch integration testing
* force-push risk and execution
* repository recovery
* history legibility as a *result* of mutation (shaping it as it's made is
  covered by Commit/Branch Discipline in `gitter`)

This skill does **not** own:

* initial repository inspection, ownership determination, or multi-agent
  isolation planning — see `gitter`
* product requirements, application architecture, or whether a fix is
  behaviorally correct
* PR approval policy, reviewer authority, or release management

---

## Activation

Use this skill whenever the task involves or may require:

* merge, rebase, squash, reset, revert, cherry-pick, force push
* resolving a conflict, textual or semantic
* combining, collapsing, or reordering commits
* testing whether several branches compose safely
* anything described as "lost commits," "something got overwritten," a
  rebase or merge that "went wrong," or an unexpectedly detached HEAD
* preparing repository state for review after `gitter` has
  produced a recommendation requiring mutation

If repository state is uncertain when this skill is invoked, defer to
`gitter` first — or, in Recovery Mode below, treat
re-establishing truth as the first step of recovery itself.

---

## Modes

### Change Mode

Use for intended repository mutations: creating branches, committing,
merging, rebasing, squashing, amending, reverting, cherry-picking, moving
worktrees, pushing rewritten history.

Default:

> Change the smallest state necessary while preserving a way back.

### Integration Mode

Use to determine whether independently authored changes compose safely.

Integration state should live in a disposable worktree, a temporary
integration branch, or an isolated test checkout — **never** in a source
branch. Never mutate source branches merely to discover whether they
integrate; that turns a question into an accident.

### Recovery Mode

Use when:

* ancestry no longer makes sense
* commits appear missing
* changes were made on the wrong branch
* a rebase or merge went wrong
* unrelated work was overwritten
* HEAD is unexpectedly detached
* branch ownership is unclear
* multiple workers collided
* history was rewritten accidentally

Default:

> Stop mutating. Reconstruct facts. Only then act.

---

## Mutation Gate

Before any destructive or history-changing operation, answer:

```text
0. Is the Truth Packet still fresh? (observed_at vs. now, fingerprints,
   explicit invalidation conditions — see schemas/repository-truth-packet.schema.json)

1. What exact state will change?

2. What exact state must remain untouched?

3. Is the target state definitely owned by this task?

4. Could another worker depend on this history?

5. Is this history already remotely visible?

6. Is review, CI, or automation referencing the current SHA?

7. Is there a recovery anchor?

8. Can the goal be achieved less destructively?

9. What verification proves the operation produced the intended result?
```

If important answers are unknown:

> Do not rewrite history. Go back to `gitter` and re-establish
> what's actually there.

---

## Risk Classes

**LOW** — read-only inspection, creating an isolated worktree, creating a new
private branch, committing bounded local changes. Normal verification
suffices.

**MODERATE** — merging the target branch into private work, cherry-picking
known commits, reverting local changes, moving commits between private
branches. Require explicit ancestry and ownership verification before
proceeding.

**HIGH** — interactive rebase, squash of shared commits, amend after
publication, branch reset, force push, deleting branches with unique commits.
Require confirmed ownership, known remote state, a recovery anchor, an exact
intended target SHA, and post-operation verification.

**CRITICAL** — rewriting another worker's active branch, hard-resetting an
unclear working tree, deleting the only known reference to commits,
force-pushing without knowing remote divergence, cleaning files of unknown
ownership.

Default for CRITICAL:

> Do not execute. Isolate or recover first.

---

## Squash Decision

Squash when several commits together represent one semantic change *and* the
intermediate commits carry no enduring value on their own:

* immediate typo correction
* a forgotten test belonging to the previous commit
* temporary instrumentation
* mechanical repair of the immediately preceding implementation
* implementation attempts superseded within the same private change

Do not squash commits that represent separate behavior, migration stages,
independent rollback points, distinct compatibility layers, independently
reviewable fixes, or separately meaningful evidence.

Goal: coherent history, not a minimal commit count.

---

## Rebase Decision

Rebase only when **all** of the following hold:

```text
base changed materially
AND
alignment matters
AND
history is safe to rewrite
AND
benefit exceeds review/coordination cost
```

Valid reasons: resolving real base conflicts, testing changed base
semantics, removing obsolete branch dependencies, preparing private work
before review, simplifying privately owned construction history.

Invalid reasons: the dashboard says "behind," the branch feels old, cleaner
graph aesthetics, ritual freshness, automatic agent habit.

Shared, already-reviewed history should generally favor additive correction
over rewrite.

---

## Merge Decision

Merge when preserving actual integration history is useful, branch history
should not be rewritten, collaboration state makes rebase inappropriate, or
repository conventions require it.

The decision follows actual collaboration state, not stylistic preference.

---

## Cherry-Pick Discipline

Before cherry-picking, determine:

```text
What behavior does this commit require?

Does it depend on earlier commits?

Does the destination provide the same surrounding assumptions?

Does the test environment still exercise the same behavior?

Will this duplicate an implementation already present?
```

A clean textual cherry-pick does not establish semantic independence.

---

## Revert Discipline

Prefer revert over history erasure when undoing shared work. A revert must:

* identify the behavior being undone
* preserve auditability
* account for subsequent changes
* avoid unintentionally reverting unrelated follow-up work
* be validated against current HEAD, not the HEAD that existed when the
  original commit landed

---

## Conflict Resolution

A conflict is not resolved merely because conflict markers disappear.

For any meaningful conflict, identify:

```text
branch-side intent
base-side intent
branch-side invariant
base-side invariant
required combined behavior
```

Then resolve and validate against that combined behavior. Never blindly
choose "ours," "theirs," "newer," "shorter," or "whichever compiles" unless
the discarded side is demonstrably irrelevant.

### Semantic Conflict Detection

Two branches can touch different files, merge cleanly, and have independent
ancestry — and still conflict semantically. Watch for branches that both
modify: lifecycle state, routing policy, schema assumptions, synchronization
rules, authentication, trust boundaries, ownership boundaries, API
contracts, resource accounting, or persistence semantics.

```text
no textual conflict ≠ no semantic conflict
```

---

## Integration Work

Use disposable integration state to test merge ordering, conflict behavior,
combined tests, duplicate implementations, schema interactions, performance
interactions, migration interactions, API assumptions, dependency
assumptions, and semantic coupling:

```text
Branch A ─┐
Branch B ─┼→ temporary integration state → validation
Branch C ─┘
```

Do not automatically convert successful synthetic integration into the final
authoring history — integration state is evidence, not a shortcut to a merge
commit.

---

## Recovery Anchors

Before any destructive operation, preserve one or more of: the remote
branch, a temporary backup branch, a known commit SHA, reflog reachability,
a temporary tag, an isolated worktree, or a temporary integration branch.

Riskier operations (HIGH/CRITICAL) require stronger anchors. No destructive
mutation should depend solely on remembering where HEAD used to be.

---

## Recovery Protocol

When repository state becomes unclear:

```text
STOP
 ↓
Do not reset
Do not clean
Do not rebase again
Do not force push
 ↓
Inspect (hand back to gitter if needed)
 ↓
Locate authoritative commits
 ↓
Identify ownership
 ↓
Determine last known-good state
 ↓
Create a recovery anchor
 ↓
Reconstruct intentionally
 ↓
Validate
```

Repository confusion compounds when mutation continues. The first move in
recovery is always to stop mutating, not to try one more fix.

---

## Command Success Is Not Completion

After any mutation, verify the **resulting** state, not just the exit code.

**After commit:** correct branch? correct files? correct parent? clean
expected state?

**After rebase:** expected ancestry? expected commit set? no missing
semantic changes?

**After merge:** expected parents? expected combined content? relevant
tests still pass?

**After push:** correct remote? correct branch? remote SHA matches the
expected SHA?

**After reset/recovery:** required commits still reachable? unrelated state
preserved?

---

## Stop Conditions

Stop mutating and return to inspection or recovery when:

* branch ownership becomes unclear mid-operation
* active work cannot be attributed
* HEAD unexpectedly changes
* another worker may have modified relevant state
* operation results differ from expectations
* a recovery anchor cannot be established
* ancestry is no longer understood
* the operator reports contradictory repository state
* conflict resolution would require architectural assumptions not
  established by evidence

---

## Evidence Packet

When this skill completes meaningful work, emit the typed handoff packet in
the common envelope (`schemas/handoff-packet.schema.json`, composed by
`schemas/repository-evidence-packet.schema.json`). Domain data lives in
`payload`; envelope fields are canonical and never re-declared:

```yaml
packet_id:
packet_type: repository_evidence_packet
schema_version:
producer: getter
task_id:
subject_ref:
observed_at:
input_state:             # state established by the consumed truth packet
output_state:            # validated state after the mutation
evidence_refs:           # the observations that justify the resulting state
unknowns:
blockers:
authority:
invalidated_by:
recommended_next:

payload:
  repository:
    branch:
    head_sha:
    target_base:
    merge_base:

  operation:
    action:
    previous_state:
    resulting_state:

  safety:
    unrelated_work_preserved:
    rewrite_performed:
    recovery_anchor:
    concurrent_worker_risk:

  validation:
    repository_checks:
    behavioral_checks:

  remote:
    pushed:
    remote_branch:
    remote_sha:
```

Unknown values should be reported as unknown. Do not fabricate certainty.

---

## Anti-Patterns

This skill rejects:

* habitual force pushes, rebases, or squashes done out of routine rather
  than a stated reason
* `reset --hard` used as general cleanup
* blind "ours"/"theirs" conflict resolution
* rewriting shared history for aesthetic reasons
* assuming push success proves correct remote state
* treating a command's exit code as proof of semantic correctness
* continuing to mutate after unexpected state appears mid-operation
* treating "no merge conflict" as proof of independence
* converting a successful synthetic integration test directly into
  authoring history without deliberate reconsideration

---

## Completion Standard

This skill's phase is complete when the resulting repository state is:

* validated after mutation
* aligned with the intended ancestry
* free of accidental unrelated work
* accompanied by a recovery anchor for anything HIGH risk or above
* understandable to another engineer from the Evidence Packet alone
* safe for the next workflow stage (review, CI, further work)

Final principle:

> Preserve truth before preserving prettiness. Safe, legible history beats
> an aesthetically perfect one every time.
