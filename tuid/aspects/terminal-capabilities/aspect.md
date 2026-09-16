# Aspect: Terminal Capabilities

Treat terminal features as capability-dependent and **progressively detected,
never assumed**. Modern terminals expose enhanced keyboard events, focus
reporting, bracketed paste, mouse protocols, hyperlinks, clipboard, graphics —
with varying support.

## Capability inventory

```text
ANSI styling · 16/256/truecolor · alternate screen · cursor addressing
mouse tracking · focus reporting · bracketed paste · enhanced keyboard
OSC hyperlinks · clipboard integration · desktop notification · raster graphics
```

## Capability policy

For each optional capability choose:

```text
REQUIRED  — application cannot sensibly operate without it
PREFERRED — use when available; maintain fallback
OPTIONAL  — enhancement only
DISABLED  — application intentionally does not use it
```

## Progressive enhancement

```text
enhanced keyboard available → yes → enable richer bindings
                            → no  → maintain functional legacy bindings
```

Do not make core functionality dependent on obscure terminal extensions unless
the application's environment explicitly guarantees them. The effective
environment is captured in the TerminalProfile primitive
(`../../primitives/terminal-profile/`); protocol mechanics in `../../protocols/`.
