# Protocol: Focus Reporting

Terminal reports focus gain/loss events to the application.

- Uses: pause polling/animation on blur, prompt on return, flush pending state.
- Capability-gated; must be disabled on exit (lifecycle restoration).
- Focus loss during async operations is a robustness test case — reported focus events interact with pending-state design.
