"""Durable state and packet stores for CognitiveStateWork."""
from __future__ import annotations

import copy
import hashlib
import json
import jsonschema
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
import yaml

if __package__:
    from .errors import PacketValidationError, TransitionError
    from .resources import (ROOT, _load_yaml, _local_schema_registry,
                            _package_resource, _schema_text)
    from .evidence import evaluate_freshness
else:
    from errors import PacketValidationError, TransitionError
    from resources import (ROOT, _load_yaml, _local_schema_registry,
                           _package_resource, _schema_text)
    from evidence import evaluate_freshness

class SubjectStateStore:
    """Durable authoritative current state plus append-only history.

    Identity is namespace/application/subject/statework/contract-version. Writers
    use compare-and-swap revisions; stale writers must re-inspect rather than
    overwrite a newer state.
    """
    def __init__(self, path: Path) -> None:
        source = Path(path)
        self.legacy_path = source if source.suffix.lower() == ".json" else None
        self.path = source.with_suffix(".sqlite3") if self.legacy_path else source
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        database = sqlite3.connect(self.path, timeout=5.0)
        database.row_factory = sqlite3.Row
        database.execute("PRAGMA busy_timeout=5000")
        return database

    def history_for(self, identity: Mapping[str, Any], *,
                    maximum: int = 4096) -> tuple[dict[str, Any], ...]:
        """Return the bounded append-only history for one workflow identity.

        Workflow authorities use this public projection when they need to
        revalidate durable transitions against current evidence. Keeping the
        query here lets alternate state stores implement the same contract
        without exposing SQLite connections or table names.
        """
        if type(maximum) is not int or not 1 <= maximum <= 4096:
            raise TransitionError("subject history bound must be between 1 and 4096")
        subject_key = self.key(identity)
        with self._connect() as database:
            rows = database.execute(
                "SELECT event_json FROM subject_history "
                "WHERE subject_key=? ORDER BY event_id LIMIT ?",
                (subject_key, maximum + 1),
            ).fetchall()
        if len(rows) > maximum:
            raise TransitionError("subject history exceeds its inspection bound")
        events: list[dict[str, Any]] = []
        for row in rows:
            try:
                event = json.loads(row[0])
            except (TypeError, json.JSONDecodeError) as exc:
                raise TransitionError("subject history contains invalid JSON") from exc
            if not isinstance(event, Mapping):
                raise TransitionError("subject history event is malformed")
            events.append(dict(event))
        return tuple(events)

    def _initialize(self) -> None:
        with self._connect() as database:
            # New authorities can be opened concurrently by independent host
            # workers. SQLite may report SQLITE_BUSY while the first process
            # changes a fresh file from DELETE to WAL mode, even with its busy
            # handler configured. Retry this one-time setup with a short
            # handler so concurrent startup stays bounded.
            database.execute("PRAGMA busy_timeout=100")
            deadline = time.monotonic() + 5.0
            retry_delay = 0.01
            while True:
                try:
                    database.execute("PRAGMA journal_mode=WAL")
                    break
                except sqlite3.OperationalError as exc:
                    message = str(exc).lower()
                    if ("locked" not in message and "busy" not in message) or (
                            time.monotonic() >= deadline):
                        raise
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 0.2)
            database.execute("PRAGMA busy_timeout=5000")
            database.executescript("""
                CREATE TABLE IF NOT EXISTS store_metadata (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS subjects (
                    subject_key TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS subject_history (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_key TEXT,
                    event_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS subject_history_scope_order
                    ON subject_history(subject_key, event_id);
            """)
            database.execute("BEGIN IMMEDIATE")
            migrated = database.execute(
                "SELECT value FROM store_metadata WHERE key='legacy_json_import_v1'").fetchone()
            if migrated is None:
                try:
                    legacy = self._read_legacy()
                    for key, record in legacy["subjects"].items():
                        database.execute(
                            "INSERT OR IGNORE INTO subjects "
                            "(subject_key, revision, record_json) VALUES (?, ?, ?)",
                            (key, int(record.get("revision", 0)),
                             json.dumps(record, sort_keys=True, separators=(",", ":"))))
                    for event in legacy.get("history", ()):
                        identity = event.get("identity") if isinstance(event, dict) else None
                        subject_key = (self.key(identity) if isinstance(identity, Mapping)
                                       else None)
                        database.execute(
                            "INSERT INTO subject_history(subject_key, event_json) VALUES (?, ?)",
                            (subject_key, json.dumps(event, sort_keys=True,
                                                     separators=(",", ":"))))
                    database.execute(
                        "INSERT INTO store_metadata(key, value) VALUES (?, ?)",
                        ("legacy_json_import_v1", "complete"))
                except Exception:
                    database.rollback()
                    raise
            database.commit()
        os.chmod(self.path, 0o600)

    def _read_legacy(self) -> dict[str, Any]:
        if self.legacy_path is None or not self.legacy_path.exists():
            return {"version": 1, "subjects": {}, "history": []}
        try:
            data = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TransitionError("subject state store is unreadable") from exc
        if (not isinstance(data, dict) or not isinstance(data.get("subjects"), dict)
                or not isinstance(data.get("history", []), list)):
            raise TransitionError("subject state store has invalid structure")
        return data

    @staticmethod
    def key(identity: Mapping[str, Any]) -> str:
        fields = [identity.get(name) for name in (
            "namespace_id", "application_id", "application_instance_id",
            "workflow_id", "subject_ref", "statework_id", "contract_version")]
        if any(not isinstance(value, str) or not value for value in fields):
            raise TransitionError(
                "subject state identity requires namespace, application, application instance, "
                "workflow, subject, StateWork, and contract version")
        return json.dumps(dict(zip((
            "namespace_id", "application_id", "application_instance_id",
            "workflow_id", "subject_ref", "statework_id", "contract_version"), fields)),
            sort_keys=True, separators=(",", ":"))

    def get(self, identity: Mapping[str, Any]) -> Dict[str, Any]:
        key = self.key(identity)
        with self._connect() as database:
            row = database.execute(
                "SELECT record_json FROM subjects WHERE subject_key=?", (key,)
            ).fetchone()
        return (dict(json.loads(row[0])) if row is not None
                else {"state": None, "revision": 0})

    def initialize_workflow(self, identity: Mapping[str, Any], *, engine_kind: str,
                            initial_data: Mapping[str, Any]) -> Dict[str, Any]:
        key = self.key(identity)
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            row = database.execute(
                "SELECT record_json FROM subjects WHERE subject_key=?", (key,)
            ).fetchone()
            current = json.loads(row[0]) if row is not None else None
            if current is None:
                current = dict(identity)
                current.update({"engine_kind": engine_kind,
                                "workflow_data": copy.deepcopy(dict(initial_data)),
                                "revision": 0,
                                "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})
                database.execute(
                    "INSERT INTO subjects(subject_key, revision, record_json) VALUES (?, ?, ?)",
                    (key, 0, json.dumps(current, sort_keys=True, separators=(",", ":"))))
            elif current.get("engine_kind", engine_kind) != engine_kind:
                database.rollback()
                raise TransitionError("workflow engine kind differs from persisted identity")
            database.commit()
            return dict(current)

    def commit_workflow(self, identity: Mapping[str, Any], *, expected_revision: int,
                        engine_kind: str, workflow_data: Mapping[str, Any],
                        transition: Mapping[str, Any]) -> Dict[str, Any]:
        key = self.key(identity)
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            row = database.execute(
                "SELECT record_json FROM subjects WHERE subject_key=?", (key,)
            ).fetchone()
            current = json.loads(row[0]) if row is not None else {"revision": 0}
            if int(current.get("revision", 0)) != int(expected_revision):
                database.rollback()
                raise TransitionError(
                    f"workflow revision conflict: expected {expected_revision}, "
                    f"found {current.get('revision', 0)}; re-inspect required")
            if current.get("engine_kind", engine_kind) != engine_kind:
                database.rollback()
                raise TransitionError("workflow engine kind differs from persisted identity")
            revision = int(expected_revision) + 1
            updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            record = dict(identity)
            record.update({"engine_kind": engine_kind,
                           "workflow_data": copy.deepcopy(dict(workflow_data)),
                           "revision": revision, "updated_at": updated_at})
            event = {
                "identity": dict(identity), "engine_kind": engine_kind,
                "revision": revision, "recorded_at": updated_at,
                "transition": copy.deepcopy(dict(transition))}
            database.execute(
                "INSERT INTO subjects(subject_key, revision, record_json) VALUES (?, ?, ?) "
                "ON CONFLICT(subject_key) DO UPDATE SET revision=excluded.revision, "
                "record_json=excluded.record_json",
                (key, revision, json.dumps(record, sort_keys=True, separators=(",", ":"))))
            database.execute(
                "INSERT INTO subject_history(subject_key, event_json) VALUES (?, ?)",
                (key, json.dumps(event, sort_keys=True, separators=(",", ":"))))
            database.commit()
            return dict(record)

    def commit(self, identity: Mapping[str, Any], *, expected_revision: int,
               new_state: str, transition: Mapping[str, Any],
               fact_ledger: Optional[Iterable[Mapping[str, Any]]] = None
               ) -> Dict[str, Any]:
        key = self.key(identity)
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            row = database.execute(
                "SELECT record_json FROM subjects WHERE subject_key=?", (key,)
            ).fetchone()
            current = (json.loads(row[0]) if row is not None
                       else {"state": None, "revision": 0})
            if int(current.get("revision", 0)) != int(expected_revision):
                database.rollback()
                raise TransitionError(f"subject state revision conflict: expected {expected_revision}, found {current.get('revision', 0)}; re-inspect required")
            revision = int(expected_revision) + 1
            recorded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            record = dict(identity); record.update({"state": new_state, "revision": revision, "updated_at": recorded_at})
            if fact_ledger is not None:
                record["fact_ledger"] = copy.deepcopy(list(fact_ledger))
            event = {"identity": dict(identity), "from_state": current.get("state"),
                     "to_state": new_state, "revision": revision,
                     "recorded_at": recorded_at, "transition": dict(transition)}
            database.execute(
                "INSERT INTO subjects(subject_key, revision, record_json) VALUES (?, ?, ?) "
                "ON CONFLICT(subject_key) DO UPDATE SET revision=excluded.revision, "
                "record_json=excluded.record_json",
                (key, revision, json.dumps(record, sort_keys=True, separators=(",", ":"))))
            database.execute(
                "INSERT INTO subject_history(subject_key, event_json) VALUES (?, ?)",
                (key, json.dumps(event, sort_keys=True, separators=(",", ":"))))
            database.commit()
            return record

class PacketStore:
    """Validated typed handoff packets. Presence alone is never truth."""

    def __init__(self, packets: Optional[Iterable[Dict[str, Any]]] = None,
                 packet_registry_path: Optional[Path] = None,
                 storage_path: Optional[Path] = None,
                 secure_storage_dir: bool = False,
                 packet_registry_data: Optional[Mapping[str, Any]] = None,
                 packet_schemas: Optional[Mapping[str, Mapping[str, Any]]] = None) -> None:
        registry_path = packet_registry_path
        if packet_registry_data is not None:
            data = dict(packet_registry_data)
            registry_schema_text = _schema_text("packet-registry.schema.json")
        elif registry_path is None:
            registry_resource = _package_resource("schemas/packet-registry.yaml")
            data = yaml.safe_load(registry_resource.read_text(encoding="utf-8")) if registry_resource else _load_yaml(ROOT / "schemas" / "packet-registry.yaml")
            registry_schema_text = _schema_text("packet-registry.schema.json")
        else:
            data = _load_yaml(registry_path)
            registry_schema = registry_path.with_name("packet-registry.schema.json")
            registry_schema_text = registry_schema.read_text(encoding="utf-8") if registry_schema.exists() else None
        if registry_schema_text:
            jsonschema.validate(
                instance=data, schema=json.loads(registry_schema_text))
        self.registry: Dict[str, Dict[str, Any]] = data.get("packets", {})
        self.packet_schemas = {str(key): dict(value)
                               for key, value in (packet_schemas or {}).items()}
        self._packets: Dict[str, Dict[str, Any]] = {}
        self._digests: Dict[str, str] = {}
        self.revision = 0
        source = Path(storage_path) if storage_path else None
        self.legacy_storage_path = (
            source if source is not None and source.suffix.lower() == ".json" else None)
        self.storage_path = (
            source.with_suffix(".sqlite3")
            if source is not None and source.suffix.lower() == ".json" else source)
        self.secure_storage_dir = bool(secure_storage_dir)
        if self.storage_path is not None:
            self._initialize_persistence()
            self._load_persistent()
        for packet in packets or []:
            self.put(packet)

    def _validate(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        packet_type = packet.get("packet_type")
        meta = self.registry.get(packet_type)
        if not meta:
            raise PacketValidationError(f"unknown packet type {packet_type!r}")
        if packet.get("producer") != meta.get("producer"):
            raise PacketValidationError(
                f"packet {packet_type!r} producer {packet.get('producer')!r} "
                f"is not registered producer {meta.get('producer')!r}")
        if packet.get("schema_version") != str(meta.get("schema_version")):
            raise PacketValidationError(
                f"packet {packet_type!r} schema version mismatch")
        schema = self.packet_schemas.get(str(packet_type))
        if schema is None:
            schema = json.loads(_schema_text(str(meta.get("schema"))))
        validator = jsonschema.Draft202012Validator(
            schema, registry=_local_schema_registry(),
            format_checker=jsonschema.FormatChecker())
        errors = sorted(validator.iter_errors(packet), key=lambda e: list(e.path))
        if errors:
            raise PacketValidationError(errors[0].message)
        from datetime import datetime
        try:
            datetime.fromisoformat(packet["observed_at"].replace("Z", "+00:00"))
        except Exception as exc:
            raise PacketValidationError(f"invalid observed_at: {exc}") from exc
        return packet

    @staticmethod
    def _packet_digest(packet: Mapping[str, Any]) -> str:
        return hashlib.sha256(json.dumps(
            packet, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")).hexdigest()

    def _connect(self) -> sqlite3.Connection:
        if self.storage_path is None:
            raise PacketValidationError("packet store has no durable database")
        database = sqlite3.connect(self.storage_path, timeout=5.0)
        database.row_factory = sqlite3.Row
        database.execute("PRAGMA busy_timeout=5000")
        return database

    def _initialize_persistence(self) -> None:
        assert self.storage_path is not None
        self.storage_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.secure_storage_dir:
            os.chmod(self.storage_path.parent, 0o700)
        with self._connect() as database:
            database.execute("PRAGMA journal_mode=WAL")
            database.executescript("""
                CREATE TABLE IF NOT EXISTS packet_store_metadata (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS stored_packets (
                    packet_id TEXT PRIMARY KEY,
                    packet_json TEXT NOT NULL,
                    content_digest TEXT NOT NULL
                );
            """)
            database.execute("BEGIN IMMEDIATE")
            imported = database.execute(
                "SELECT value FROM packet_store_metadata WHERE key='legacy_json_import_v1'").fetchone()
            if imported is None:
                try:
                    revision = 0
                    legacy_path = self.legacy_storage_path
                    if legacy_path is not None and legacy_path.exists():
                        try:
                            stored = json.loads(legacy_path.read_text(encoding="utf-8"))
                            revision = int(stored.get("revision", 0) or 0)
                            packets = stored.get("packets", [])
                            if isinstance(packets, dict):
                                packets = list(packets.values())
                            for raw_packet in packets:
                                packet = self._validate(copy.deepcopy(raw_packet))
                                digest = self._packet_digest(packet)
                                database.execute(
                                    "INSERT OR IGNORE INTO stored_packets "
                                    "(packet_id, packet_json, content_digest) VALUES (?, ?, ?)",
                                    (packet["packet_id"], json.dumps(
                                        packet, sort_keys=True, separators=(",", ":")), digest))
                        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
                            raise PacketValidationError(
                                f"persistent packet authority is unreadable: {legacy_path}") from exc
                    database.execute(
                        "INSERT INTO packet_store_metadata(key, value) VALUES ('revision', ?)",
                        (str(revision),))
                    database.execute(
                        "INSERT INTO packet_store_metadata(key, value) VALUES (?, ?)",
                        ("legacy_json_import_v1", "complete"))
                except Exception:
                    database.rollback()
                    raise
            database.commit()
        os.chmod(self.storage_path, 0o600)

    def _load_persistent(self) -> None:
        assert self.storage_path is not None
        try:
            with self._connect() as database:
                row = database.execute(
                    "SELECT value FROM packet_store_metadata WHERE key='revision'").fetchone()
                self.revision = int(row[0]) if row is not None else 0
                packets = database.execute(
                    "SELECT packet_json, content_digest FROM stored_packets ORDER BY packet_id"
                ).fetchall()
            loaded_packets: Dict[str, Dict[str, Any]] = {}
            loaded_digests: Dict[str, str] = {}
            for row in packets:
                packet = self._validate(json.loads(row["packet_json"]))
                digest = self._packet_digest(packet)
                if digest != row["content_digest"]:
                    raise PacketValidationError("persistent packet content digest is invalid")
                loaded_packets[packet["packet_id"]] = packet
                loaded_digests[packet["packet_id"]] = digest
            self._packets, self._digests = loaded_packets, loaded_digests
        except (OSError, sqlite3.Error, json.JSONDecodeError, TypeError, ValueError) as exc:
            if isinstance(exc, PacketValidationError):
                raise
            raise PacketValidationError(
                f"persistent packet authority is unreadable: {self.storage_path}") from exc

    def _persist(self, packets: Mapping[str, Dict[str, Any]],
                 digests: Mapping[str, str], expected_revision: int) -> int:
        if self.storage_path is None:
            return expected_revision
        if (not set(self._packets).issubset(packets)
                or any(digests.get(key) != digest
                       for key, digest in self._digests.items())):
            raise PacketValidationError(
                "packet store entries are immutable and cannot be removed or replaced")
        self.storage_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.secure_storage_dir:
            os.chmod(self.storage_path.parent, 0o700)
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            row = database.execute(
                "SELECT value FROM packet_store_metadata WHERE key='revision'").fetchone()
            current_revision = int(row[0]) if row is not None else 0
            if current_revision != expected_revision:
                database.rollback()
                raise PacketValidationError(
                    f"packet store revision conflict: expected {expected_revision}, "
                    f"found {current_revision}; reload before writing")
            durable = {row["packet_id"]: row["content_digest"]
                       for row in database.execute(
                           "SELECT packet_id, content_digest FROM stored_packets")}
            if (not set(durable).issubset(packets)
                    or any(digests.get(key) != digest
                           for key, digest in durable.items())):
                database.rollback()
                raise PacketValidationError(
                    "durable packet entries are immutable and cannot be removed or replaced")
            additions = [key for key in packets if key not in durable]
            database.executemany(
                "INSERT INTO stored_packets(packet_id, packet_json, content_digest) "
                "VALUES (?, ?, ?)",
                [(key, json.dumps(packets[key], sort_keys=True, separators=(",", ":")),
                  digests[key]) for key in additions])
            database.execute(
                "UPDATE packet_store_metadata SET value=? WHERE key='revision'",
                (str(expected_revision + 1),))
            database.commit()
        os.chmod(self.storage_path, 0o600)
        return expected_revision + 1

    def put(self, packet: Dict[str, Any], *, persist: bool = True) -> str:
        candidate = copy.deepcopy(packet)
        self._validate(candidate)
        packet_id = candidate["packet_id"]
        digest = self._packet_digest(candidate)
        if packet_id in self._packets and self._digests[packet_id] != digest:
            raise PacketValidationError(f"conflicting packet id {packet_id!r}")
        candidate_packets = copy.deepcopy(self._packets)
        candidate_digests = dict(self._digests)
        candidate_packets[packet_id] = candidate
        candidate_digests[packet_id] = digest
        if persist:
            new_revision = self._persist(candidate_packets, candidate_digests, self.revision)
            self._packets = candidate_packets
            self._digests = candidate_digests
            self.revision = new_revision
        else:
            self._packets = candidate_packets
            self._digests = candidate_digests
        return packet_id

    def reload(self) -> None:
        """Replace live state from durable storage after a conflict."""
        if self.storage_path is None or not self.storage_path.exists():
            raise PacketValidationError("packet store has no durable state to reload")
        self._load_persistent()

    def get(self, packet_id: str) -> Optional[Dict[str, Any]]:
        """Read a previously validated typed packet by immutable identity."""
        packet = self._packets.get(packet_id)
        return copy.deepcopy(packet) if packet is not None else None

    def packet_digest(self, packet_id: str) -> Optional[str]:
        return self._digests.get(packet_id)

    def get_schema_valid(self, packet_type: str, *, task_id: str,
                         subject_ref: str) -> Optional[Dict[str, Any]]:
        """Return the newest schema-valid, task/subject-bound packet.

        This deliberately does not claim that external reality is current.
        Callers that use a truth packet to authorize a transition must use
        :meth:`get_current` with an observation context.
        """
        matches = [
            p for p in self._packets.values()
            if p.get("packet_type") == packet_type and p.get("task_id") == task_id
            and p.get("subject_ref") == subject_ref and not p.get("invalidated_by")
        ]
        if not matches:
            return None
        return copy.deepcopy(sorted(matches, key=lambda p: datetime.fromisoformat(
            p["observed_at"].replace("Z", "+00:00")), reverse=True)[0])

    def validate_current(self, packet: Dict[str, Any], *, observation_context: Optional[Mapping[str, Any]] = None) -> bool:
        """Run the packet-type freshness validator against current reality."""
        context = dict(observation_context or {})
        meta = self.registry.get(packet.get("packet_type"), {})
        freshness = meta.get("freshness")
        if freshness is None and meta.get("freshness_validator"):
            freshness = {"strategy": "trusted_validator",
                         "validator_id": meta.get("freshness_validator")}
        if freshness == "immutable":
            return True
        required_context = list(meta.get("required_context") or [])
        required_any_context = list(meta.get("required_any_context") or [])
        if required_context and not all(context.get(key) for key in required_context):
            return False
        if required_any_context and not any(context.get(key) for key in required_any_context):
            return False
        return evaluate_freshness(packet, context, freshness)

    def get_current(self, packet_type: str, *, task_id: str, subject_ref: str,
                    observation_context: Optional[Mapping[str, Any]] = None) -> Optional[Dict[str, Any]]:
        matches = [
            copy.deepcopy(packet) for packet in self._packets.values()
            if packet.get("packet_type") == packet_type
            and packet.get("task_id") == task_id
            and packet.get("subject_ref") == subject_ref
            and not packet.get("invalidated_by")
        ]
        valid = [packet for packet in matches
                 if self.validate_current(packet, observation_context=observation_context)]
        if not valid:
            return None
        return sorted(valid, key=lambda p: datetime.fromisoformat(
            p["observed_at"].replace("Z", "+00:00")), reverse=True)[0]

    def fresh_repository_truth(self, *, task_id: str, expected_subject_ref: str,
                               repository_freshness: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        """Return repository truth only when every freshness dimension matches."""
        observation_context = {"repository_freshness": dict(repository_freshness)}
        packet = self.get_current(
            "repository_truth_packet", task_id=task_id,
            subject_ref=expected_subject_ref, observation_context=observation_context)
        if packet is None:
            return None
        freshness = packet.get("payload", {}).get("freshness", {})
        if dict(freshness) != dict(repository_freshness):
            return None
        return packet
