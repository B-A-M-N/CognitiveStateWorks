# Primitive: Component

An independently understandable interaction/render unit.

```yaml
component:
  identity:
  responsibility:
  state:
  inputs:
  outputs:
  region:
  focusable:
  interactive:
  children:
```

A useful boundary separates at least one meaningful concern: state,
interaction, rendering, lifecycle, reuse, testing. Do not create components
merely to split files. Interactive components carry the full component
contract (`../../components/`); this primitive is the structural vocabulary.
