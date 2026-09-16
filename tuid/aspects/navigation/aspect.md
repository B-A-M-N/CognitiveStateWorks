# Aspect: Navigation

Distinguish the four kinds — do not overload one concept to mean all four:

```text
APPLICATION NAVIGATION  moving between major surfaces
COMPONENT NAVIGATION    moving inside a list/table/tree
FOCUS NAVIGATION        moving input ownership
VIEWPORT NAVIGATION     scrolling visible content
```

Selection and scrolling are related but not identical (see `../scrolling/`):
moving selection may scroll it into view; manual scrolling need not always
move selection.

Navigation coherence is part of the completion standard — the user must
always be able to answer "where am I, how did I get here, how do I go back."
Navigation defects attribute via `../../flows/debug/` (usually
interaction/focus layer, not render).
