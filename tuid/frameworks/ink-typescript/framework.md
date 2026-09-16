# Framework Adapter: Ink / TypeScript

Natural decomposition follows React:

```text
components + props + state + hooks + context + renderer
```

Do not import imperative terminal mutation into a declarative component tree
without strong reason. Input hooks must have explicit activation/context where
several potential handlers coexist — implicit hook ordering is not an input
routing contract (`../../aspects/keyboard/`).

Render purity maps naturally to `state → deterministic view`; effect hooks
carry async work back through state, not direct output.
