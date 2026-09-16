# Primitive: TerminalProfile

The effective terminal environment — detected, not assumed.

```yaml
terminal_profile:
  width:
  height:
  color:      { monochrome: ansi16: ansi256: truecolor: }
  input:      { keyboard: enhanced_keyboard: mouse: focus_reporting: bracketed_paste: }
  output:     { alternate_screen: hyperlinks: clipboard: graphics: }
  environment:{ terminal: multiplexer: ssh: platform: }
```

Do not assume every capability exists. Detection is progressive
(`../../aspects/terminal-capabilities/`); the profile is the record of what
was detected and what policy was applied. Capture the profile with defect
reports — capability assumptions explain a whole class of "works on my
machine" defects. Profile matrix tests exercise representative profiles
(`../../testing/terminal-profile-tests/`).
