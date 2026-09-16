# Component: Progress

Progress indication for bounded or unbounded work.

```yaml
purpose: communicate operation progress/useful state
state:      kind (determinate/indeterminate) · value · label · cancellable
states:     pending · active · done · failed · cancelled
concerns:
  - determinate when quantity known; honest indeterminate otherwise (no fake percentages)
  - label carries information: "Indexing 4,251 files…" not just motion (../../aspects/feedback-states/)
  - cancellation affordance when the operation can be cancelled
  - completed/failed must be visible — progress that vanishes on completion hides outcome
overflow:   label truncation preserving the informative part
```
