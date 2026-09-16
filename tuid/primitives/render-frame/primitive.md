# Primitive: RenderFrame

The complete visible representation at a point in application state.

```yaml
frame:
  size:
  component_regions:
  cursor:
  focus:
  style_profile:
  contents:
  overlays:
```

Validation dimensions for rendered output. A frame is the unit of snapshot
tests and layout invariant assertions. The render pipeline maps
state + terminal profile + viewport → layout → components → frame → terminal
backend; the frame is what the evidence hierarchy calls a *render snapshot*
— regression evidence, not interaction evidence.
