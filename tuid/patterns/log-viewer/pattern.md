# Pattern: Log Viewer

Explicit handling required for:

follow mode · pause · search · filtering · severity · wrapping · horizontal
overflow · timestamps · **high event rate** · **bounded memory**.

## Notes

- Follow vs pause: user scroll implies pause (or explicit control); resume is
  explicit or unmistakable.
- High-rate streams coalesce renders — the rendering budget applies
  (`../../aspects/performance/`).
- Buffer eviction policy explicit; "1M lines in memory" is the anti-pattern.
- Severity never color-only; wrapping vs horizontal scroll is a chosen
  policy. Timestamp display survives narrow widths via degradation, not
  removal of meaning.
