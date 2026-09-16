# Primitive: Visual Token

The atomic unit of visual language: a semantic style consumed by components
rather than literal colors/borders/symbols.

```yaml
visual_token:
  role:        # surface · text_primary · accent · focus · selection · success · warning · danger · border_active …
  color:       # resolved per terminal color capability
  emphasis:    # weight/dim/bold/italic where supported
  symbol:      # where glyph assumptions are risky, configurable
```

Components consume roles, never literals — so themes change in one place and
color-depth degradation resolves in one place. The theme token table lives in
`../../aspects/color-theme/`; the design system aggregates tokens
(`../../flows/design/`). Role-based rendering also enforces "color is not
meaning": paired symbols/text live at the token level.
