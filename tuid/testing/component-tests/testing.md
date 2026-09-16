# Testing: Component Tests

Layer 2. Verify per component: state, input handling, emitted messages/actions,
overflow, boundary behavior. Each interactive component's contract
(`../../components/`) is the test checklist — states, focusability, overflow
policy. Component tests compose into state-transition tests at the surface
level.
