# Testing: Layout Tests

Layer 3. Fixed terminal dimensions; test wide, standard, narrow, minimum
supported, and awkward odd sizes.

**Assert region invariants, not merely pretty snapshots:**

```text
regions do not overlap unexpectedly
modal fits viewport
primary content remains nonzero
hidden pane cannot own focus
```

Snapshot-diffing a correct layout is regression evidence; invariant
assertions are correctness evidence. Both belong here.
