# Aspect: Layout

Layout owns spatial structure:

```text
available rectangle → major regions → component regions → content rectangles
```

## Dimension kinds

fixed · minimum · maximum · proportional · weighted · content-derived ·
remaining-space. Do not depend on arbitrary string-length guesses where the
framework provides measured dimensions.

## Hierarchy signals, in preference order

1. placement
2. spacing
3. alignment
4. emphasis
5. grouping
6. borders

Do not use borders as the primary solution to every grouping problem. Nested
border soup is usually weaker than deliberate spacing and region hierarchy.

## Clutter audit

```yaml
clutter:
  nested_border_depth:
  persistent_status_markers:
  simultaneous_highlights:
  competing_accent_colors:
  chrome_to_content_ratio:
  duplicated_labels:
  duplicated_shortcuts:
```

Removal test:

> If removing an element does not reduce comprehension or capability, why is
> it permanently consuming terminal cells?

Overflow behavior is part of region design — truncation, scroll, wrap, or
overlay is a deliberate choice per region, not an accident. Responsive
behavior is owned by `../responsive/`; spatial region math by
`../../primitives/region/`.
