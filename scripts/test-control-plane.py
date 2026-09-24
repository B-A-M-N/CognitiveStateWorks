#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.control_plane import PacketStore, TransitionEngine  # noqa: E402


def main() -> int:
    failures = []
    def check(name, condition, detail=""):
        print(f"  [{'ok' if condition else 'FAIL'}] {name} {detail if not condition else ''}")
        if not condition:
            failures.append(name)

    packet = json.loads((ROOT / "fixtures" / "fixtures-valid.ndjson").read_text().splitlines()[0])
    store = PacketStore([packet])
    valid = store.get_schema_valid(packet["packet_type"], task_id=packet["task_id"], subject_ref=packet["subject_ref"])
    check("packet store accepts schema-valid packet", valid and valid["packet_id"] == packet["packet_id"])
    packet["payload"]["change"]["intended_task"] = "caller mutation"
    valid["payload"]["change"]["intended_task"] = "returned mutation"
    reread = store.get(packet["packet_id"])
    check("packet store isolates caller and reader mutations",
          reread["payload"]["change"]["intended_task"] != "caller mutation"
          and reread["payload"]["change"]["intended_task"] != "returned mutation")
    check("packet store records stable content digest",
          bool(store.packet_digest(packet["packet_id"])))
    try:
        PacketStore([{}])
        check("packet store rejects empty packet", False)
    except Exception:
        check("packet store rejects empty packet", True)
    try:
        PacketStore([dict(packet, packet_id="wrong-producer", producer="getter")])
        check("packet store rejects wrong producer", False)
    except Exception:
        check("packet store rejects wrong producer", True)

    engine = TransitionEngine({
        "initial_state": "UNKNOWN",
        "states": ["UNKNOWN", "OBSERVED", "MODELED"],
        "completion_states": ["MODELED"],
        "transitions": [
            {"from": "UNKNOWN", "to": "OBSERVED", "trigger": "discover", "required_evidence": ["e1"]},
            {"from": "OBSERVED", "to": "MODELED", "trigger": "model", "required_evidence": ["e1", "e2"]},
        ],
    })
    legal_evidence = [
        {"ref": "a", "kind": "e1", "subject_ref": "subject", "observed_at": "2026-01-01T00:00:00Z"},
        {"ref": "b", "kind": "e2", "subject_ref": "subject", "observed_at": "2026-01-01T00:00:00Z"},
    ]
    check("legal transition with typed evidence allowed",
          engine.transition("subject", "OBSERVED", "MODELED", trigger="model", evidence_refs=legal_evidence).allowed)
    check("wrong evidence count blocked",
          not engine.transition("subject", "OBSERVED", "MODELED", trigger="model",
                                evidence_refs=legal_evidence[:1]).allowed)
    check("fake count evidence blocked",
          not engine.transition("subject", "OBSERVED", "MODELED", trigger="model",
                                evidence_refs=["garbage1", "garbage2"]).allowed)
    check("invalidated evidence blocked",
          not engine.transition("subject", "OBSERVED", "MODELED", trigger="model",
                                evidence_refs=[dict(item, invalidated=True) for item in legal_evidence]).allowed)
    wildcard = TransitionEngine({
        "initial_state": "UNKNOWN", "states": ["UNKNOWN", "DEFECTIVE"],
        "completion_states": ["UNKNOWN"],
        "transitions": [{"from": "*", "to": "DEFECTIVE", "trigger": "violation",
                         "required_evidence": ["violation"]}],
    })
    check("wildcard transition executes",
          wildcard.transition("s", "UNKNOWN", "DEFECTIVE", trigger="violation",
                              evidence_refs=[{"ref": "v", "kind": "violation", "subject_ref": "s",
                                              "observed_at": "2026-01-01T00:00:00Z"}]).allowed)
    check("undeclared transition blocked",
          not engine.transition("subject", "UNKNOWN", "MODELED", trigger="model", evidence_refs=["a", "b"]).allowed)
    reordered = TransitionEngine({
        "initial_state": "UNKNOWN", "states": ["OBSERVED", "UNKNOWN"],
        "completion_states": ["OBSERVED"],
        "transitions": [{"from": "UNKNOWN", "to": "OBSERVED", "trigger": "discover",
                         "required_evidence": ["e1"]}],
    })
    check("transition initialization honors initial_state",
          reordered.transition("subject", "UNKNOWN", "OBSERVED", trigger="discover",
                               evidence_refs=legal_evidence[:1]).allowed)
    mismatched_subject = [dict(item, subject_ref="other") for item in legal_evidence]
    check("evidence for another subject blocked",
          not engine.transition("subject", "OBSERVED", "MODELED", trigger="model",
                                evidence_refs=mismatched_subject).allowed)
    try:
        TransitionEngine({"states": ["UNKNOWN"], "transitions": []})
        check("missing initial_state rejected", False)
    except Exception:
        check("missing initial_state rejected", True)

    from scripts.control_plane import EvidenceStore, SubjectStateStore, TransitionError
    import tempfile
    with tempfile.TemporaryDirectory(prefix="statework-subject-") as raw:
        store = SubjectStateStore(Path(raw) / "subjects.json")
        identity = {"namespace_id": "ns", "application_id": "app", "subject_ref": "repo", "statework_id": "gitter", "contract_version": "1.1.0"}
        check("subject state starts absent", store.get(identity)["state"] is None)
        first = store.commit(identity, expected_revision=0, new_state="UNKNOWN", transition={"trigger": "bootstrap"})
        check("subject state commits with revision", first["revision"] == 1 and first["state"] == "UNKNOWN")
        try:
            store.commit(identity, expected_revision=0, new_state="OBSERVED", transition={"trigger": "stale"})
            check("stale subject writer rejected", False)
        except TransitionError:
            check("stale subject writer rejected", True)
        attested = EvidenceStore([{"ref": "auth-1", "kind": "authority", "subject_ref": "repo", "observed_at": "2026-01-01T00:00:00Z", "issuer": "host:authorization", "validator": "host-authorization-v1", "schema": "authority-record-v1"}])
        contract = {"initial_state": "UNKNOWN", "states": ["UNKNOWN", "CHANGING"], "transitions": [{"from": "UNKNOWN", "to": "CHANGING", "trigger": "mutate", "required_evidence": ["authority"]}]}
        engine = TransitionEngine(contract, evidence_registry={"kinds": {"authority": {"authoritative": True, "allowed_issuers": ["host:authorization"], "validator": "host-authorization-v1", "schema": "authority-record-v1"}}}, evidence_store=attested)
        check("trusted reference authorizes consequential transition", engine.transition("repo", "UNKNOWN", "CHANGING", trigger="mutate", evidence_refs=["auth-1"]).allowed)
        check("caller-declared authority metadata is not trusted", not engine.transition("repo", "UNKNOWN", "CHANGING", trigger="mutate", evidence_refs=[{"ref": "forged-auth", "kind": "authority", "subject_ref": "repo", "observed_at": "2026-01-01T00:00:00Z", "issuer": "host:authorization", "validator": "host-authorization-v1", "schema": "authority-record-v1"}]).allowed)
        from scripts.control_plane import StandaloneStateWorkController
        controller = StandaloneStateWorkController(contract=contract, identity=identity, state_store=store, evidence_store=attested, evidence_registry={"kinds": {"authority": {"authoritative": True, "allowed_issuers": ["host:authorization"], "validator": "host-authorization-v1", "schema": "authority-record-v1"}}})
        revision = controller.inspect()["revision"]
        check("standalone controller owns initial subject state", controller.inspect()["state"] == "UNKNOWN")
        check("standalone controller allows attested transition", controller.request_transition(to_state="CHANGING", trigger="mutate", evidence_refs=["auth-1"], expected_revision=revision).allowed)
        try:
            controller.request_transition(to_state="CHANGING", trigger="mutate", evidence_refs=["auth-1"], expected_revision=revision)
            check("standalone controller rejects stale revision", False)
        except TransitionError:
            check("standalone controller rejects stale revision", True)
        from scripts.control_plane import StandaloneHostInterface
        host = StandaloneHostInterface(root=ROOT, state_path=Path(raw) / "host-state.json", evidence_path=Path(raw) / "host-evidence.json")
        check("host interface resolves installed StateWork", host.resolve_statework("gitter")["id"] == "gitter")
        check("host interface starts durable subject", host.start_or_resume(statework_id="gitter", identity=identity)["state"] == "UNKNOWN")
        host.submit_attested_observation({"ref": "obs-1", "kind": "discovery", "subject_ref": "repo", "observed_at": "2026-01-01T00:00:00Z"})
        host2 = StandaloneHostInterface(root=ROOT, state_path=Path(raw) / "host-state.json", evidence_path=host.evidence_path)
        check("host evidence survives interface restart", host2.evidence_store.resolve(["obs-1"])[0]["ref"] == "obs-1")
        host3 = StandaloneHostInterface(root=ROOT, state_path=Path(raw) / "host-state.json", evidence_path=host.evidence_path)
        check("host evidence remains idempotent after second restart", host3.evidence_store.resolve(["obs-1"])[0]["ref"] == "obs-1")
        host.evidence_store.invalidate("obs-1")
        host.evidence_store.save(host.evidence_path)
        host4 = StandaloneHostInterface(root=ROOT, state_path=Path(raw) / "host-state.json", evidence_path=host.evidence_path)
        invalidated = host4.evidence_store.resolve(["obs-1"])[0]
        check("invalidation survives restart and remains auditable", invalidated["invalidated"] is True and bool(invalidated.get("attestation_digest")))
        try:
            host.start_or_resume(statework_id="infrae", identity=identity)
            check("mismatched StateWork identity rejected", False)
        except TransitionError:
            check("mismatched StateWork identity rejected", True)

    print("pass" if not failures else f"FAILED {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
