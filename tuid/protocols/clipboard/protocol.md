# Protocol: Clipboard Integration

OSC 52 and similar terminal clipboard bridges.

- Optional enhancement; direct clipboard access varies by terminal, SSH, and multiplexer.
- Copy affordances must have keyboard-reachable equivalents (select + copy, explicit copy action).
- Security-sensitive content (secrets in logs, tokens) must not be placed on the clipboard casually — an explicit user action only.
