# Component: Modal

Input-capturing overlay.

```yaml
purpose: focused interaction that must intercept underlying input
state:      content · open/closed · internal focus
states:     open · closing · (content states as applicable)
concerns:
  - modal focus sequence: remember previous focus → focus modal → capture modal-relevant actions → close → restore prior valid focus (../../aspects/focus/)
  - input must NOT leak to the underlying surface — leaking `q` etc. is HIGH severity
  - destructive confirmation must be unambiguous (no ambiguous destructive trigger)
  - fits viewport at every supported size; smaller viewports get the TOO_SMALL/scroll policy
  - render order ≠ input precedence — overlay stack defines both explicitly
overflow:   internal scroll; minimum region contract
```
