# Pattern: Picker

Optimized loop:

```text
type → filter → move → select → exit
```

## Notes

- Usually **inline** mode — avoid dashboard-level chrome on a three-second
  selection workflow.
- Empty-match state distinct from empty-set state; Escape/cancel semantics
  crisp (cancel vs select-nothing vs dismiss).
- Selection returns through a controlled state transition; the underlying
  context stays intact (overlay/summoned interaction).
- Fuzzy-filter input is a text-input component; paste into the filter is not
  typing.
