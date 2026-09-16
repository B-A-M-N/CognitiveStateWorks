---
name: gitter
description: >
  Repository-state observation, truth-establishment, ownership, and change-isolation
  discipline. Use before any Git work begins — creating branches, starting a task,
  coordinating multiple agents or humans in one repository, or judging whether
  current repository state is safe to touch. Trigger whenever work involves
  branches, commits, worktrees, HEAD, concurrent workers sharing a repository,
  stale or ambiguous branch state, or determining what actually changed versus
  what is merely believed to have changed. Also trigger the moment repository
  state is uncertain, or when an operator reports something like "another agent
  touched this," "that branch changed," "this looks mixed together," or "you're
  on the wrong branch" — treat these as state-invalidating observations requiring
  re-inspection, not as casual remarks. This skill owns OBSERVE, MODEL, CLASSIFY
  RISK, and REPORT. It hands off to the companion skill `getter`
  for the actual MUTATE, VERIFY, and recovery work once truth has been established
  and an action has been recommended.
---

# Gitter — Git Repository Truth & Isolation Discipline

> **StateWork note.** Gitter is the observation half of a Repository
> StateWork, implementing `../PROTOCOL.md` implicitly: Inspect Mode is its
> observation rule (element 3), the Truth Packet and Standard Assessment are
> its handoff contracts (element 13), and operator state-invalidating
> observations are its invalidation rules (element 9). Mutation-phase
> transitions belong to the companion skill `getter`.

## Purpose

This skill governs **knowing what is actually true about a repository** before
anyone — human or agent — acts on it.

Its job is to ensure that, before a single command mutates anything, the
following are established and legible:

* what state currently exists
* who owns it
* what is isolated from what
* what would be lost if something went wrong
* what a competent second engineer would need to know to trust the next move

It is a **reasoning discipline**, not a command cookbook. It does not tell you
*how* to rebase, squash, or resolve a conflict — that is the job of its
companion skill, `getter`, which takes over once this skill has
produced a Repository Truth Packet and a recommendation.

Applies regardless of programming language, repository host, branching
strategy, CI platform, project architecture, or whether the actor is a human
or an agent — and regardless of how many workers are operating concurrently.

---

## Core Doctrine

> Git state is evidence.

Repository state must be **observed** before it is **acted on**. Every
meaningful engagement with a repository follows the same pipeline:

```text
OBSERVE
   ↓
MODEL
   ↓
CLASSIFY RISK
   ↓
REPORT  ──────→  (hand off to getter for MUTATE → VERIFY)
```

None of the following are proof of correctness on their own:

* a command having executed successfully
* a clean working tree
* a branch name
* a conflict-free merge (proves nothing about semantic independence)
* a green CI run on a stale ref
* another worker's silence in their terminal

If you find yourself about to recommend a mutation without having actually
looked, stop. Looking is the whole point of this skill.

---

## Scope

This skill owns:

* repository inspection
* branch state and topology
* ancestry and merge-base reasoning
* local/remote divergence
* dirty-state assessment
* worktree isolation
* branch and commit ownership
* concurrent-worker isolation planning
* branch discipline
* commit discipline
* the Repository Truth Packet and Standard Assessment (the report/recommendation)

This skill does **not** own:

* choosing or executing rebase, merge, squash, cherry-pick, or revert mechanics
* conflict resolution
* integration testing across branches
* recovery from a bad state that has already occurred
* force-push execution
* release management, PR approval policy, or product correctness

Those belong to `getter`. This skill's output — the Truth
Packet and a recommended action — is that skill's input.

---

## Activation

Use this skill whenever the task involves or may involve:

* Git, branch, commit, HEAD, worktree, detached HEAD
* multiple agents or humans editing one repository
* stale branches, branch divergence, or "is this safe to touch?"
* determining what changed, who changed it, or why a branch looks the way it does
* preparing repository state for review or for a mutation
* any point where repository state is **uncertain**

Uncertainty is itself sufficient reason to invoke this skill. You do not need
a mutation already planned to justify inspecting first.

---

## Operator Observations Are Evidence

When the operator says something like:

* "another agent touched this"
* "that branch changed"
* "there are commits missing"
* "this looks mixed together"
* "this branch should not contain that"
* "you are on the wrong branch"
* "this was already fixed"
* "something got overwritten"

do not treat the statement as a casual aside. Treat it as a
**state-invalidating observation**. Re-run inspection on the relevant facts
before continuing with anything — including a mutation already in progress
under the companion skill.

Do not defend a previous model of repository state merely because an earlier
command appeared to succeed. A model built five minutes ago may already be
wrong.

---

## Inspect Mode

This skill operates almost exclusively in **Inspect Mode**: read-only
repository analysis.

Use it to determine:

* current branch and HEAD
* ancestry and merge-base relationships
* local/remote divergence
* worktree state and which worker owns which worktree
* branch and commit ownership
* commit composition (what a branch actually contains, not what its name implies)
* whether a mutation — if one is later proposed — would even be safe

Default posture:

> Observe first. Change nothing. Recommend, don't act.

If a mutation turns out to be warranted, the recommendation is handed to
`getter`, which re-verifies relevant facts before acting (state
can shift between the recommendation and the act, especially with concurrent
workers).

---

## Repository Truth Packet

Before handing off any nontrivial recommendation, emit the typed handoff
packet in the **common envelope** (`schemas/handoff-packet.schema.json`,
composed by `schemas/repository-truth-packet.schema.json`). Domain data lives
in `payload`; envelope fields are canonical and never re-declared:

```yaml
packet_id:             # unique id for this emission
packet_type: repository_truth_packet
schema_version:        # version of the packet schema
producer: gitter
task_id:
subject_ref:           # what this packet is about (branch, repo, commit)
observed_at:           # ISO-8601 UTC observation time
input_state:
output_state: observed
evidence_refs:         # the observations that justify this packet
unknowns:
blockers:
authority:             # ownership/authorization basis for the observation
invalidated_by:        # observation that would reopen this state
recommended_next: getter

payload:
  repository:
    root:
    current_branch:
    head_sha:
    tracking_branch:
    target_base:
    target_base_sha:
    merge_base:
    working_tree:
    staged_changes:
    unstaged_changes:
    untracked_files:
    ahead:
    behind:
    local_only_commits:
    remote_only_commits:
    active_worktrees:
    operation_in_progress:
    remote_visibility:

  change:
    intended_task:
    branch_purpose:
    logical_change_units:
    unrelated_changes:
    unexpected_commits:
    branch_owner:
    concurrent_workers:
    rewrite_risk:
    integration_risk:

  freshness:
    repo_identity:              # stable identity of the observed repository
    observed_head:              # HEAD sha observed at observed_at
    working_tree_fingerprint:   # fingerprint of the working tree at observed_at
    active_worktree_snapshot:   # inventory of active worktrees at observed_at
    remote_state_fingerprint:   # remote state if it was observed
    invalidation_conditions:    # what would make this packet stale
```

Not every field needs to be displayed to the operator. But you must know
enough of them to justify whatever you recommend next — an unfilled field you
can't reason about is a reason to keep inspecting, not to guess.

---

## Change Isolation

Every independent implementation should have its own repository-state
boundary.

Preferred:

```text
task
  ↓
branch
  ↓
worktree
  ↓
worker
```

For concurrent work:

```text
Worker A → Worktree A → Branch A
Worker B → Worktree B → Branch B
Worker C → Worktree C → Branch C
```

Not:

```text
Worker A ─┐
Worker B ─┼→ same checkout
Worker C ─┘
```

Separate terminals are not isolation. Separate processes are not isolation.
Separate agent sessions are not isolation. Only separate worktrees (or
equivalently disjoint checkouts) provide real isolation of working-tree state.

---

## Ownership Discipline

Before recommending any change to an existing branch, determine:

```text
Who owns the branch?

Who else may be using it?

Is another worker currently operating on it?

Has it been pushed?

Is it under review?

Are external systems referencing its SHAs?

Is the current actor authorized to touch its history?
```

Unknown ownership means:

> Recommend additive or isolated work, not rewriting work.

Ownership questions are answered by evidence (recent commits, remote
tracking state, active worktree locks, what the operator has told you) — not
assumed from branch naming conventions or from silence.

---

## Multi-Agent Rules

When multiple workers operate in one repository:

1. Give independent work independent branches.
2. Prefer independent worktrees.
3. Do not opportunistically clean another worker's branch.
4. Do not reset another worker's state.
5. Do not amend another worker's commits without authority.
6. Do not rebase another worker's branch without authority.
7. Do not force-push another worker's branch without authority.
8. Do not assume another worker has stopped just because its terminal is quiet.
9. Treat each worker's reported HEAD as evidence requiring verification, not
   as fact on assertion.
10. Coordinate shared-base refreshes rather than refreshing unilaterally.
11. Perform cross-branch integration in disposable integration state (see
    `getter`), never by mutating a source branch.
12. Report branch and exact HEAD after any handoff.
13. Report whether anything was pushed.
14. Distinguish local-only state from remote-visible state explicitly.
15. Re-inspect before recommending a mutation if another worker may have
    changed relevant state since your last observation.

These rules exist because in a multi-agent context, "it looked fine a moment
ago" is not evidence — state can move under you between messages.

---

## Branch Discipline

A healthy branch has:

* one understandable purpose
* a known target base
* understandable ancestry
* bounded scope
* known ownership
* no unexplained commits
* no accidental dependency on unrelated local state
* no hidden cross-task changes

If a branch's stated purpose and its actual contents diverge:

> Stop adding work to it and flag the mismatch before anything else happens.

A branch must not become a dumping ground for unrelated work, even when that
would be the path of least resistance in the moment.

---

## Commit Discipline

A good commit represents a defensible unit of intent. A reviewer — human or
agent — should be able to answer, from the commit alone:

```text
What changed?

Why?

What invariant or behavior does it protect?

What evidence belongs to it?

Would reverting it independently make conceptual sense?
```

Avoid **meaningless fragmentation** — a string of commits that are merely
construction history for one semantic change and carry no independent value:

```text
fix
fix test
actually fix test
lint
oops
remove debug
```

Avoid **meaningless consolidation** — do not combine unrelated bugs, unrelated
formatting, architecture cleanup, mechanical churn, independent migrations, or
separate rollback units into one commit merely to reduce commit count.

Whether a run of small commits should later be squashed is a mutation
decision — see `getter`. This section only governs how commits
should be *shaped* as they're made, before any rewriting is considered.

---

## Standard Assessment (Report)

When this skill completes its work on a piece of repository state, report:

```yaml
state:
  branch:
  head:
  target:
  merge_base:
  dirty:
  divergence:
  remote_visibility:
  active_worktrees:

change_shape:
  logical_units:
  unrelated_changes:
  unexpected_commits:
  rewrite_risk:
  ownership_risk:

recommendation:
  action:
  reason:
  handoff_to: getter   # when the recommended action requires mutation
```

Possible `action` values at this stage are recommendations, not
executions — `keep`, `isolate`, `split`, `commit`, or a note that mutation
(squash / rebase / merge / cherry-pick / revert / recover / integrate-test)
is warranted and should be handed to the companion skill with this packet
attached.

Unknown values should be reported as unknown. Do not fabricate certainty to
make the packet look more complete than the evidence supports.

---

## Anti-Patterns

This skill rejects:

* treating branch names as evidence of branch contents
* treating a clean working tree as evidence of correctness
* same-checkout multi-agent work
* hiding unrelated changes inside a convenient commit
* opportunistic cleanup of another worker's branch
* assuming a quiet terminal means a worker has stopped
* recommending a mutation without having actually inspected current state
* re-using a stale Truth Packet after an operator's state-invalidating
  observation instead of re-inspecting

---

## Completion Standard

This skill's phase is complete when the relevant repository state is:

* known
* attributable
* isolated appropriately
* understandable to another engineer
* summarized in a Truth Packet and Standard Assessment fit to hand to
  `getter` (or to close out, if no mutation is warranted)

Final principle:

> You cannot safely change what you have not first understood. Establish
> truth before recommending anything that touches it.
