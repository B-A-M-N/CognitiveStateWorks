# Aspect: Observability

TUI-specific observability: making interface behavior diagnosable without
corrupting the interface.

## Rules

- Debug output goes somewhere that does not corrupt the owned terminal surface — a log file, a debug pane, or a separate stream. Never `println` into a rendered interface (`../rendering/`).
- Trace which layer owns a defect: state → interaction → focus → layout → render → terminal → async → capability (`../../flows/debug/`).
- Focus traces, event logs, and render-frame captures are diagnostic evidence for interaction defects.
- Capture the TerminalProfile with defect reports — capability assumptions explain a class of "works on my machine" defects.

## Evidence

Observability supports the evidence hierarchy but does not replace it:
internal traces are source-level evidence; rendered/runtime evidence is still
required for visual and interaction claims.
