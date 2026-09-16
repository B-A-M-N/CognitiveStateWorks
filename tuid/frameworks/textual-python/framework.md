# Framework Adapter: Textual / Python

Natural decomposition:

```text
App
├── Screens
├── Widgets
├── Messages / Events
├── Reactive state
├── Workers
└── Layout / styles
```

Textual treats widgets as screen regions with their own event behavior and
queued messages — respect framework ownership of the application lifecycle.

Use headless application testing and interaction-driving facilities
(`run_test()` / Pilot) where appropriate — they map to the interaction-test
layer without a real PTY. Workers are the async-effect mechanism: results
return through messages, keeping the stale-result rule enforceable.
