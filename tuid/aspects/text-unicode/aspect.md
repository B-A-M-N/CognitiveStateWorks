# Aspect: Text & Unicode

## Display width ≠ string length

Reason about: code points, grapheme clusters, display width, combining marks,
emoji, wide characters, ambiguous-width characters, truncation, ellipsis.
Do not equate byte length or ordinary string length with occupied terminal
cells — width bugs corrupt alignment and can shift layout.

## Typography

Terminal typography is constrained by the user's emulator and font. `tui'd`
controls: case, weight where available, dim/bold/italic where supported,
spacing, punctuation, symbols, text hierarchy. It does not control font
family the way a browser UI does.

Do not assume Nerd Font glyphs exist unless the user/application explicitly
opts in. Configurable symbols where glyph assumptions are risky (accessibility
consideration). Robustness testing must include Unicode-heavy content and
1-column-wide labels (`../../flows/review/` robustness dimension).
