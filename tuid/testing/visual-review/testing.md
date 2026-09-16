# Testing: Visual Review

Rendered review inspects: hierarchy, density, alignment, spacing, clipping,
overflow, focus, selection, error state, loading state, empty state, narrow
state, wide state.

**A screenshot of the default happy state is weak evidence.** Visual review
is a human or agent pass over rendered output across states and sizes — it
complements layout invariant tests rather than replacing them. Feed findings
into the review flow's dimensions (`../../flows/review/`); severity there,
not aesthetic preference.
