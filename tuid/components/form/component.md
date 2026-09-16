# Component: Form

Multi-field input workflow.

```yaml
purpose: structured multi-field entry with validation and submission
state:      current field · values · validation (per field) · submission (pending/error)
states:     initial · editing · validating · submitting · submitted · submission-error
concerns:
  - form state separates: current field / values / validation / submission pending / submission error (pattern: ../../patterns/form-workflow/)
  - focus order predictable; focus survives validation re-render
  - validation policy matches input — do not reject every incomplete value while typing
  - submission disabled/allowed policy explicit; double-submit guarded
  - error display per field + summary; errors actionable (what/how to fix)
overflow:   scrolling form body with focus-follows-scroll
```
