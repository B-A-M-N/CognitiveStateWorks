# Aspect: Robustness

Test awkward states — real data is hostile to decorative mockups:

```text
1-column-wide labels · very long filenames · long hostnames · Unicode
empty collections · 10,000-row collections · rapid resize
zero/near-zero content region · slow dependency · failed dependency
lost connection · duplicate events · cancelled operations · terminal focus loss
```

Robustness findings map to review dimensions (`../../flows/review/`):
overflow behavior, feedback states, async cancellation, viewport minimums.
Virtualization for large collections belongs to the data-browser pattern
(`../../patterns/data-browser/`); bounded memory for high-rate streams to the
log-viewer pattern (`../../patterns/log-viewer/`).
