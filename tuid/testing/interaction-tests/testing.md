# Testing: Interaction Tests

Layer 5. Drive key presses, key sequences, focus, text, paste, resize, mouse
where supported, modal transitions. Assert **both**:

```text
state  +  visible result
```

A key handler that updates state correctly but renders nothing is caught
here, not by state tests alone. Modal focus capture/restore, resize-during-
interaction, and stale-result races are the high-value scenarios.
