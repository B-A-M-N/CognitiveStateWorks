# Aspect: Color & Theme

## Semantic tokens, not literal colors

Components consume semantic roles:

```yaml
theme:
  surface:  surface_elevated:
  text_primary:  text_secondary:  text_muted:
  accent:  focus:  selection:
  success:  warning:  danger:  info:
  border:  border_active:
```

Avoid every component independently choosing literal colors.

## Color is not meaning

Do not encode `red = failed, green = passed` with no other distinction. Use
symbolic or textual differentiation (`✗ Failed` / `✓ Passed`). Color-only
semantics is an accessibility failure and a LOW-severity-profile defect with
HIGH impact for color-blind users.

## Terminal color profiles

Plan for truecolor · 256 · 16 · monochrome. Graceful degradation matters more
than pretending every terminal is identical. Profile detection and policy
(REQUIRED/PREFERRED/OPTIONAL/DISABLED) live in
`../terminal-capabilities/`; protocol mechanics in
`../../protocols/color-capabilities/`.
