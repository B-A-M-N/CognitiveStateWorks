---
flow: review
required_specialists: []
optional_specialists: []
---
# Flow: Review (audit an existing TUI)

Review dimensions remain **separate** — do not collapse everything into a
meaningless `8.4/10`:

```text
Architecture · Interaction · Navigation · Focus · Layout · Responsiveness
Visual hierarchy · Components · Feedback states · Accessibility
Terminal compatibility · Rendering stability · Performance · Testing
Robustness
```

## Audit matrix

```yaml
architecture:  { state_ownership: component_boundaries: event_flow: }
interaction:   { key_routing: discoverability: cancellation: }
focus:         { ownership: order: visibility: }
layout:        { hierarchy: resizing: overflow: }
components:    { consistency: state_completeness: }
visual:        { hierarchy: density: color: text: }
terminal:      { lifecycle: capabilities: restoration: }
async:         { blocking: cancellation: stale_results: }
performance:   { redraw: responsiveness: }
accessibility: { keyboard: focus: color_independence: }
testing:       { state: layout: snapshots: interaction: pty: }
status:        { blockers: significant: polish: }
```

## Severity

- **BLOCKER** — terminal left corrupted after exit; primary workflow impossible; input routed to a dangerous hidden action; component inaccessible at a supported viewport; destructive action triggered ambiguously.
- **HIGH** — focus disappears; modal leaks input; resize destroys state; common async race displays wrong data; persistent severe flicker.
- **MEDIUM** — weak hierarchy; inefficient navigation; confusing empty states; poor narrow-layout behavior.
- **LOW** — cosmetic alignment; minor styling inconsistency; optional polish.

Do not turn cosmetic preferences into critical defects.

## Output

Concrete operational output — findings by dimension with severity, evidence
lines (reproduction sizes, focus traces, PTY reproduction), and an ordered
`Next` that fixes interaction invariants before visual polish:

```text
State: ORANGE
Blocking:  [invariant violations, with reproduction evidence]
High:      [defects, no invariant violation]
Medium:    [usability]
Evidence:  [reproduced at 68×24, focus trace, PTY reproduction]
Next:      [order: interaction invariants → input precedence → polish last]
```
