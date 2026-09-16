# Component: Text

Display component for static or bound text.

```yaml
purpose: render text content within a region
states: ready · truncated · wrapped
concerns:
  - display width ≠ string length (Unicode, wide chars, combining marks) — see ../../aspects/text-unicode/
  - truncation policy (ellipsis position) and wrap policy are explicit, not accidental
  - styling via semantic theme tokens, not literal colors
overflow: truncate / wrap / clip per region contract
```
