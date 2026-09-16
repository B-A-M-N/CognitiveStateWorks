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
          engine.transition("OBSERVED", "MODELED", trigger="model", evidence_refs=legal_evidence).allowed)
    check("wrong evidence count blocked",
          not engine.transition("OBSERVED", "MODELED", trigger="model",
                                evidence_refs=legal_evidence[:1]).allowed)
    check("fake count evidence blocked",
          not engine.transition("OBSERVED", "MODELED", trigger="model",
                                evidence_refs=["garbage1", "garbage2"]).allowed)
    check("invalidated evidence blocked",
          not engine.transition("OBSERVED", "MODELED", trigger="model",
                                evidence_refs=[dict(item, invalidated=True) for item in legal_evidence]).allowed)
    wildcard = TransitionEngine({
        "initial_state": "UNKNOWN", "states": ["UNKNOWN", "DEFECTIVE"],
        "completion_states": ["UNKNOWN"],
        "transitions": [{"from": "*", "to": "DEFECTIVE", "trigger": "violation",
                         "required_evidence": ["violation"]}],
    })
    check("wildcard transition executes",
          wildcard.transition("UNKNOWN", "DEFECTIVE", trigger="violation",
                              evidence_refs=[{"ref": "v", "kind": "violation", "subject_ref": "s",
                                              "observed_at": "2026-01-01T00:00:00Z"}]).allowed)
    check("undeclared transition blocked",
          not engine.transition("UNKNOWN", "MODELED", trigger="model", evidence_refs=["a", "b"]).allowed)
    reordered = TransitionEngine({
        "initial_state": "UNKNOWN", "states": ["OBSERVED", "UNKNOWN"],
        "completion_states": ["OBSERVED"],
        "transitions": [{"from": "UNKNOWN", "to": "OBSERVED", "trigger": "discover",
                         "required_evidence": ["e1"]}],
    })
    check("transition initialization honors initial_state",
          reordered.transition("UNKNOWN", "OBSERVED", trigger="discover",
                               evidence_refs=legal_evidence[:1]).allowed)
    try:
        TransitionEngine({"states": ["UNKNOWN"], "transitions": []})
        check("missing initial_state rejected", False)
    except Exception:
        check("missing initial_state rejected", True)

    print("pass" if not failures else f"FAILED {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
