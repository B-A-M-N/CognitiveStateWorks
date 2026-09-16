# Pattern: Wizard

Multi-step form workflow.

## Required aspects

step state (current/visited/completed) · per-step validation · back/next
semantics · progress indication · step skipping policy · summary/confirm step ·
resumability policy.

## Notes

- Back must not silently discard entered data (or must warn if it does).
- Steps with async dependencies show per-step pending/error, not one global
  state.
- Completion state is explicit — the user must see the workflow ended
  successfully, and what to do next.
- Step count visible: "Step 2 of 5" beats a mystery progress bar.
