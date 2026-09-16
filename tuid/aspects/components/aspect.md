# Aspect: Components

## Component families

```text
Display   text · badge · progress · status
Navigation menu · tabs · breadcrumb · tree
Collections list · table · grid · log viewport
Input     text input · textarea · checkbox · radio · selector · form
Overlay   modal · palette · contextual help · notification
```

Concrete contracts per component live in `../` — the `components/` directory
(`../../components/`). Do not invent a custom interaction pattern when an
established component model already matches the requirement.

## Component contract

Each interactive component defines:

```yaml
component:
  purpose:
  state:
  focusable:
  selectable:
  scrollable:
  editable:
  actions:
  empty_state:
  disabled_state:
  focused_state:
  active_state:
  error_state:
  minimum_region:
  overflow:
```

## Boundary test

A useful component boundary separates at least one meaningful concern: state,
interaction, rendering, lifecycle, reuse, or testing. Do not create components
merely to split files. Every data-bearing component needs meaningful
non-happy states — a widget that only renders its ready state is incomplete.
