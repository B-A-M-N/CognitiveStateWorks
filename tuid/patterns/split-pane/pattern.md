# Pattern: Split Pane

Two or more regions with a divider.

## Required aspects

divider affordance (draggable where mouse; preset ratios where keyboard) ·
focus indication per pane · pane navigation · resize of pane vs resize of
terminal (both must work) · minimum pane sizes · overflow per pane.

## Notes

- Minimum pane sizes prevent a pane from collapsing to unusable; below
  minimum, degrade the split (collapse pane / become overlay) rather than
  render a 2-column pane.
- Pane focus must be visible; tab/pane-cycle navigation explicit.
- At narrow viewports the split itself is the first responsive casualty —
  degrade to stacked or single-pane with drawer.
- Divider resize must not violate scroll-offset or selection validity
  invariants.
