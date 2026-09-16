# Aspect: Accessibility

Terminal accessibility varies by environment. Improve what the application
controls; require consideration of:

- keyboard-only operation
- predictable focus order
- visible focus
- no color-only state
- readable contrast
- understandable labels
- optional/reducible animation where appropriate
- text equivalents for decorative symbols
- configurable symbols where glyph assumptions are risky
- usable error text

Do not claim every TUI is inherently accessible or inherently inaccessible.
**Test against the actual target environment where accessibility is a hard
requirement** — claims without target-environment evidence are an
anti-pattern.
