# Pattern: File Browser

Data browser specialized for filesystems: tree or flat listing + preview
detail.

## Required aspects

directory navigation · file selection · preview · hidden/ignore rules · path
truncation (long filenames are a robustness case) · Unicode filenames ·
refresh on external change · permission/error per entry.

## Notes

- Long filenames and deep paths: truncation with the informative end
  preserved (basename vs directory trade-off — deliberate).
- Sort order and its visibility; type icons/symbols must not be Nerd
  Font-dependent.
- Detail/preview follows selection with the stale-result rule; slow
  filesystems need loading states per selection.
