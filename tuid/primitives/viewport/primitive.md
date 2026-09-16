# Primitive: Viewport

The drawable cell surface.

```yaml
viewport:
  columns:
  rows:
  minimum_supported:
  density_class:   # WIDE · STANDARD · NARROW · CONSTRAINED · TOO_SMALL
```

Do not hard-code density classes to arbitrary universal dimensions — the
application determines its truthful minimum. `TOO_SMALL` renders a clear
minimum-size message rather than a broken interface. Density classes drive
the responsive ladder (`../../aspects/responsive/`).
