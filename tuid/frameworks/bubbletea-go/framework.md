# Framework Adapter: Bubble Tea / Go

Natural model (MVU):

```text
Model → Update(message) → Model + Command → View
```

Use framework-native lifecycle and terminal-mode handling.

**Bubble Tea v2's declarative view is the framework-specific authority** for
alternate screen, mouse mode, focus reporting, cursor, and other supported
terminal view state. Do not copy v1 lifecycle recipes into v2 blindly.

`tui'd` mapping: Update = interaction → state transitions (keep intents, not
literal keys); Commands = async effects outside the render path (stale-result
rule applies); View = deterministic render; v2 view options = capability
policy implementation point.
