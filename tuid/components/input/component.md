# Component: Text Input

Single-line editable field.

```yaml
purpose: single-line text entry
state:      value · cursor · selection · placeholder · validation
focusable:  yes (text target)
states:     empty · focused · disabled · error (validation) · read-only
concerns:
  - exactly one text field owns text input at a time (invariant)
  - paste ≠ typing — bracketed paste handling (../../aspects/text-input/)
  - cursor positioning with wide/combining characters
  - horizontal scroll when value exceeds region
  - validation timing matches input, not blindly rejecting mid-typing
overflow:   horizontal scroll with cursor kept visible
```
