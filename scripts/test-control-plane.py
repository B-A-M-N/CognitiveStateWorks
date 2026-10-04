#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.control_plane import PacketStore, TransitionEngine  # noqa: E402


def edge(origin, destination, trigger, required, *, progress="LATERAL", **metadata):
    edge_id = metadata.pop("id", f"test.{origin}.{trigger}.{destination}".lower().replace("*", "any"))
    return {
        "id": edge_id,
        "from": origin,
        "to": destination,
        "trigger": trigger,
        "required_evidence": list(required),
        "work_class": metadata.pop("work_class", "test"),
        "domain_effect": metadata.pop("domain_effect", f"enter_{destination.lower()}"),
        "progress_class": progress,
        **metadata,
    }


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
            edge("UNKNOWN", "OBSERVED", "discover", ["e1"], progress="FORWARD_PROGRESS"),
            edge("OBSERVED", "MODELED", "model", ["e1", "e2"], progress="TERMINAL"),
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
        "transitions": [edge("*", "DEFECTIVE", "violation", ["violation"],
                              progress="INVALIDATION", path_class="external")],
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
        "transitions": [edge("UNKNOWN", "OBSERVED", "discover", ["e1"], progress="TERMINAL")],
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
    try:
        TransitionEngine({"initial_state": "UNKNOWN", "states": ["UNKNOWN", "CHANGING"],
                          "transitions": [edge("UNKNOWN", "CHANGING", "mutate", ["authority"],
                                                progress="FORWARD_PROGRESS", consequential=True)]},
                         evidence_registry={"kinds": {}}, require_registered=True)
        check("unregistered consequential evidence rejected", False)
    except Exception:
        check("unregistered consequential evidence rejected", True)
    try:
        TransitionEngine({"initial_state": "UNKNOWN", "states": ["UNKNOWN", "INCIDENT"],
                          "transitions": [edge("*", "INCIDENT", "incident", ["failure"],
                                                progress="FORWARD_PROGRESS", path_class="external")]})
        check("external transition must be classified as invalidation", False)
    except Exception:
        check("external transition must be classified as invalidation", True)

    from scripts.control_plane import EvidenceStore, SubjectStateStore, TransitionError
    import tempfile
    with tempfile.TemporaryDirectory(prefix="statework-subject-") as raw:
        store = SubjectStateStore(Path(raw) / "subjects.json")
        identity = {"namespace_id": "ns", "application_id": "app", "application_instance_id": "instance", "workflow_id": "workflow", "subject_ref": "repo", "statework_id": "gitter", "contract_version": "1.1.0"}
        check("subject state starts absent", store.get(identity)["state"] is None)
        first = store.commit(identity, expected_revision=0, new_state="UNKNOWN", transition={"trigger": "bootstrap"})
        check("subject state commits with revision", first["revision"] == 1 and first["state"] == "UNKNOWN")
        try:
            store.commit(identity, expected_revision=0, new_state="OBSERVED", transition={"trigger": "stale"})
            check("stale subject writer rejected", False)
        except TransitionError:
            check("stale subject writer rejected", True)
        attested = EvidenceStore([{"ref": "auth-1", "kind": "authority", "subject_ref": "repo", "observed_at": "2026-01-01T00:00:00Z", "issuer": "host:authorization", "validator": "host-authorization-v1", "schema": "authority-record-v1"}])
        contract = {"initial_state": "UNKNOWN", "states": ["UNKNOWN", "CHANGING"], "transitions": [edge("UNKNOWN", "CHANGING", "mutate", ["authority"], progress="FORWARD_PROGRESS", consequential=True)]}
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
        packet = json.loads((ROOT / "fixtures" / "fixtures-valid.ndjson").read_text().splitlines()[0])
        check("host publishes durable packet", host.publish_packet(packet) == packet["packet_id"])
        restarted_host = StandaloneHostInterface(root=ROOT, state_path=Path(raw) / "host-state.json", evidence_path=host.evidence_path)
        check("durable packet survives host restart", packet["packet_id"] in restarted_host.packet_store._packets)
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
        freshness_store = SubjectStateStore(Path(raw) / "freshness-state.json")
        freshness_evidence = EvidenceStore([{"ref": "fresh-old", "kind": "authority", "subject_ref": "repo", "observed_at": "2020-01-01T00:00:00Z", "issuer": "host:authorization", "validator": "host-authorization-v1", "schema": "authority-record-v1"}])
        freshness_contract = {"initial_state": "UNKNOWN", "states": ["UNKNOWN", "CHANGING"], "transitions": [edge("UNKNOWN", "CHANGING", "mutate", ["authority"], progress="FORWARD_PROGRESS", consequential=True, evidence_freshness={"mode": "after_state_entry", "max_age_seconds": 60})]}
        fresh_controller = StandaloneStateWorkController(contract=freshness_contract, identity=identity, state_store=freshness_store, evidence_store=freshness_evidence, evidence_registry={"kinds": {"authority": {"authoritative": True, "allowed_issuers": ["host:authorization"], "validator": "host-authorization-v1", "schema": "authority-record-v1"}}})
        check("freshness rejects evidence predating state entry", not fresh_controller.request_transition(to_state="CHANGING", trigger="mutate", evidence_refs=["fresh-old"], expected_revision=fresh_controller.inspect()["revision"]).allowed)
        entered = datetime.fromisoformat(
            fresh_controller.inspect()["updated_at"].replace("Z", "+00:00"))
        entry = entered + timedelta(seconds=1)
        offset_observed = entry.astimezone(timezone(timedelta(hours=-5))).isoformat()
        freshness_evidence.create({"ref": "fresh-offset", "kind": "authority", "subject_ref": "repo",
                                  "observed_at": offset_observed, "issuer": "host:authorization",
                                  "validator": "host-authorization-v1", "schema": "authority-record-v1",
                                  "content_digest": "offset-evidence"})
        check("timezone-offset evidence compares by instant",
              fresh_controller.request_transition(to_state="CHANGING", trigger="mutate",
                  evidence_refs=["fresh-offset"],
                  expected_revision=fresh_controller.inspect()["revision"]).allowed)
        with tempfile.TemporaryDirectory(prefix="statework-tamper-") as tamper_raw:
            evidence_path = Path(tamper_raw) / "evidence.json"
            trusted = EvidenceStore()
            trusted.create({"ref": "attested", "kind": "authority", "subject_ref": "repo", "observed_at": "2026-01-01T00:00:00Z"})
            trusted.save(evidence_path)
            records = json.loads(evidence_path.read_text(encoding="utf-8"))
            records[0]["subject_ref"] = "forged"
            evidence_path.write_text(json.dumps(records), encoding="utf-8")
            try:
                EvidenceStore.load_attested(records)
            except TransitionError:
                pass
            else:
                raise AssertionError("altered persisted evidence was accepted")
            records[0]["subject_ref"] = "repo"
            records[0]["invalidation_events"].append({"event": "forged"})
            try:
                EvidenceStore.load_attested(records)
            except TransitionError:
                pass
            else:
                raise AssertionError("forged evidence history was accepted")
        cycle_state = SubjectStateStore(Path(raw) / "cycle-state.json")
        cycle_evidence = EvidenceStore()
        cycle_contract = {"initial_state": "A", "states": ["A", "B"], "transitions": [
            edge("A", "B", "advance", ["authority"], progress="FORWARD_PROGRESS", consequential=True, evidence_freshness={"mode": "after_state_entry"}),
            edge("B", "A", "return", ["authority"], progress="RECOVERY", consequential=True, evidence_freshness={"mode": "after_state_entry"})]}
        cycle = StandaloneStateWorkController(contract=cycle_contract, identity=identity, state_store=cycle_state, evidence_store=cycle_evidence, evidence_registry={"kinds": {"authority": {"authoritative": True, "allowed_issuers": ["host:test"], "validator": "host-test-v1", "schema": "test-evidence-v1"}}})
        cycle_evidence.create({"ref": "after-initial-a", "kind": "authority", "subject_ref": "repo", "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "issuer": "host:test", "validator": "host-test-v1", "schema": "test-evidence-v1", "content_digest": "a"})
        check("cycle A to B", cycle.request_transition(to_state="B", trigger="advance", evidence_refs=["after-initial-a"], expected_revision=cycle.inspect()["revision"]).allowed)
        cycle_evidence.create({"ref": "after-b", "kind": "authority", "subject_ref": "repo", "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "issuer": "host:test", "validator": "host-test-v1", "schema": "test-evidence-v1", "content_digest": "b"})
        check("cycle B to A", cycle.request_transition(to_state="A", trigger="return", evidence_refs=["after-b"], expected_revision=cycle.inspect()["revision"]).allowed)
        # Progress metadata: a recovery hop must not be reported as forward
        # progress, or CFW would silently reset its no-progress budget.
        progress_contract = {"initial_state": "PLANNED", "states": ["PLANNED", "CHANGING", "VERIFIED", "RECOVERY", "PLANNED2"],
            "completion_states": ["VERIFIED"],
            "normal_path": ["PLANNED", "CHANGING", "VERIFIED"],
            "transitions": [
                edge("PLANNED", "CHANGING", "start", ["authority"], progress="FORWARD_PROGRESS"),
                edge("CHANGING", "VERIFIED", "verify", ["authority"], progress="TERMINAL"),
                edge("CHANGING", "RECOVERY", "fail", ["authority"], progress="RECOVERY", path_class="recovery"),
                edge("RECOVERY", "PLANNED2", "replan", ["authority"], progress="RECOVERY", path_class="recovery")]}
        progress_kinds = {"kinds": {"authority": {"authoritative": True,
            "allowed_issuers": ["host:authorization"],
            "validator": "host-authorization-v1", "schema": "authority-record-v1"}}}
        progress_store = EvidenceStore([
            {"ref": f"pa-{n}", "kind": "authority", "subject_ref": "repo",
             "observed_at": "2026-01-01T00:00:00Z", "issuer": "host:authorization",
             "validator": "host-authorization-v1", "schema": "authority-record-v1",
             "content_digest": str(n)} for n in range(1, 9)])
        progress_engine = TransitionEngine(progress_contract,
            evidence_registry=progress_kinds, evidence_store=progress_store)
        forward = progress_engine.transition("repo", "PLANNED", "CHANGING", trigger="start",
                                            evidence_refs=["pa-1"])
        terminal = progress_engine.transition("repo", "CHANGING", "VERIFIED", trigger="verify",
                                             evidence_refs=["pa-2"])
        recovery = progress_engine.transition("repo", "CHANGING", "RECOVERY", trigger="fail",
                                             evidence_refs=["pa-3"])
        check("forward transition reports FORWARD_PROGRESS", forward.progress_class == "FORWARD_PROGRESS" and forward.is_forward_progress(), forward.progress_class)
        check("reaching completion state is terminal forward progress", terminal.progress_class == "TERMINAL" and terminal.is_forward_progress(), terminal.progress_class)
        check("recovery hop is not forward progress", recovery.progress_class == "RECOVERY" and not recovery.is_forward_progress(), recovery.progress_class)
        check("second A uses latest entry freshness", not cycle.request_transition(to_state="B", trigger="advance", evidence_refs=["after-initial-a"], expected_revision=cycle.inspect()["revision"]).allowed)

    print("pass" if not failures else f"FAILED {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
