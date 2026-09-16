# Framework Adapter: Ratatui / Rust

Natural decomposition:

```text
App state + event loop + layout + widgets + terminal backend
```

Keep state transition, event interpretation, layout calculation, and
rendering **separable enough to test independently** — this maps directly to
the test layers: state tests on app logic, layout tests on layout computation,
render tests via its test backend.

Use the test backend (or equivalent) for deterministic rendering tests — it
justifies snapshot/golden rendering as its own layer. Terminal lifecycle
(restoration, modes) belongs to the backend initialization/restore pair; test
it on the abnormal-exit path.
