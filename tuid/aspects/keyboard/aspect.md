# Aspect: Keyboard

## Physical key ≠ application intent

```text
j
DownArrow
Ctrl+N
```

may all map to `MoveNext`. The application layer cares about `MoveNext`, not
three unrelated behavior implementations.

## Input routing contract

```text
terminal input → normalize → global emergency handling → overlay stack
→ focused component → current view → application fallback
```

Every event must have understandable ownership. Make keybinding precedence
explicit or two components may react to the same event:

```text
emergency / application-global → overlay → focused input
→ focused component → current view → application
```

## Discoverability

Do not require memorizing the entire key map. Use: contextual footer, help
overlay, command palette, contextual hints, visible labels, first-use guidance
where appropriate. Avoid a permanent footer containing every possible
shortcut.

## Enhanced keyboard

Modern protocols (e.g., kitty keyboard protocol) distinguish events legacy
input cannot represent. Progressive enhancement: richer bindings when
available, functional legacy bindings always. Core functionality must not
depend on obscure extensions unless the environment guarantees them.
Protocol mechanics in `../../protocols/keyboard/`.
