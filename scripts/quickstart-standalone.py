#!/usr/bin/env python3
"""Five-minute CSW-only example using Gitter durable state and evidence."""
from __future__ import annotations
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.control_plane import StandaloneHostInterface
IDENTITY = {
    "namespace_id": "readme", "application_id": "csw-quickstart",
    "subject_ref": "repo:demo", "statework_id": "gitter", "contract_version": "1.1.0",
}
with tempfile.TemporaryDirectory(prefix="csw-quickstart-") as raw:
    state = Path(raw)
    host = StandaloneHostInterface(root=ROOT, state_path=state / "subjects.json",
                                   evidence_path=state / "evidence.json")
    initial = host.start_or_resume(statework_id="gitter", identity=IDENTITY)
    blocked = host.request_transition(
        statework_id="gitter", identity=IDENTITY, to_state="OBSERVED",
        trigger="observe", evidence_refs=[], expected_revision=initial["revision"])
    host.submit_attested_observation({
        "ref": "truth-1", "kind": "repository_truth", "subject_ref": IDENTITY["subject_ref"],
        "observed_at": "2026-09-23T00:00:00Z", "issuer": "validator:repository-truth-v1",
        "validator": "repository-truth-v1", "schema": "repository-truth-packet.schema.json",
    })
    allowed = host.request_transition(
        statework_id="gitter", identity=IDENTITY, to_state="OBSERVED",
        trigger="observe", evidence_refs=["truth-1"], expected_revision=initial["revision"])
    restarted = StandaloneHostInterface(
        root=ROOT, state_path=state / "subjects.json", evidence_path=state / "evidence.json")
    resumed = restarted.start_or_resume(statework_id="gitter", identity=IDENTITY)
    print("initial:", initial["state"], "revision", initial["revision"])
    print("transition without evidence allowed:", blocked.allowed)
    print("transition with trusted evidence allowed:", allowed.allowed)
    print("after restart:", resumed["state"], "revision", resumed["revision"])
