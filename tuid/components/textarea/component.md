# Component: Textarea

Multi-line editable field.

```yaml
purpose: multi-line text entry/editing
state:      value · cursor (line, column) · selection · scroll · history (if undo)
focusable:  yes (text target)
states:     empty · focused · disabled · error · read-only
concerns:
  - word wrap vs hard newlines — explicit policy
  - cursor visibility guaranteed under scroll; typing near edge scrolls deliberately
  - paste of large content: bounded, single undo unit where supported
  - vertical scroll policy and offset validity under resize
overflow:   wrap or horizontal scroll — chosen, not default
```
