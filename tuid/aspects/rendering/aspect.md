# Aspect: Rendering

Prefer `state → deterministic view` where framework architecture permits.
Avoid mutating domain state merely because rendering occurred. Rendering must
not invent application semantics.

## Render ownership

Exactly one coherent layer owns terminal drawing. Never allow:

```text
framework renderer + random fmt.Println + background goroutine writes
+ debug output
```

to compete for the same terminal surface. Debugging output goes somewhere
that does not corrupt the owned terminal.

## Render frame

The complete visible representation at a point in state
(`../../primitives/render-frame/`): size, component regions, cursor, focus,
style profile, contents, overlays.

## Flicker

Investigate: unnecessary full redraw · layout instability · frame clearing ·
concurrent output · rapid state toggling · size oscillation · animation
frequency · terminal protocol behavior. Do not "fix" flicker by reducing
update rate before identifying its source — that hides the defect, and
flicker attribution may land in state, layout, render, or terminal layers
(`../../flows/debug/`).
