# Pattern: Form Workflow

Form state separates:

```text
current field · values · validation · submission · pending state · submission error
```

## Notes

- Validation policy matches the input: do not blindly reject every incomplete
  value while the user is still typing.
- Focus order predictable; focus survives validation re-renders.
- Submission: explicit trigger, double-submit guarded, pending state visible,
  error actionable (what failed, how to fix, retry affordance).
- Long forms scroll with focus-follows-scroll; multi-step variants are wizards
  (`../wizard/`).
