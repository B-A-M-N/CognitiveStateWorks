# Framework Selection

Choose based on project requirements and ecosystem — never popularity alone.

```yaml
selection:
  implementation_language:
  existing_codebase:
  component_model:
  styling_requirements:
  async_requirements:
  performance:
  terminal_control:
  testing:
  ecosystem:
  deployment:
```

The decision is a project decision; `tui'd` remains framework-neutral. The
domain contracts (state ownership, focus, capabilities, testing layers,
evidence hierarchy) hold under every choice — only the idioms differ. After
selection, load the matching adapter and respect its lifecycle ownership.
