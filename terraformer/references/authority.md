# Authority, evidence, and invalidation

The trusted host/operator authorizes each consequential connection. The CSW workflow-state controller decides legal transitions and persists evidence with revision checks. This skill cannot grant its own mutation rights or install a new state authority.

Host-attested evidence must cover concrete claims and exact revisions. A declared `host:statework-observation` issuer is an interface requirement, not itself independent proof. The host must implement validators for contract compatibility, end-to-end outcome, lifecycle recovery, authority integrity and compatibility. If absent, mark the applicable gate `BLOCKED` and operate advisory-only.

Re-observe affected contracts and integration paths when components change, external consumers disagree, failure behavior contradicts the model, or new revisions invalidate prior evidence. Partial integration must preserve a defined stable boundary and rollback/resume record, not claim overall completion.
