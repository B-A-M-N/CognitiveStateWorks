#!/usr/bin/env python3
"""Packet freshness executor (#17 of the review).

`observed_at` vs now is NOT freshness. A packet 20 seconds old can be stale
if HEAD changed; a 30-minute-old packet may be valid if every fingerprint is
identical. This script compares a repository truth packet against the
current repository state and reports exactly which fields must be
re-observed.

Contract fixes:
- packet schema is validated BEFORE freshness comparisons (fail closed)
- repo_identity compares canonical identities directly, never path prefixes
- working-tree fingerprint hashes actual state: HEAD + index diff +
  working-tree diff + untracked inventory, with size limits
- git command failure is explicit and fail-closed (never "clean")
- remote state: unreachable remote means remote truth is UNKNOWN, not still
  valid (fail-closed)

Usage:
    python3 scripts/validate-repository-truth.py <packet.json> [repo_dir]
"""
from __future__ import annotations

import hashlib
import json
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = _HERE if (_HERE / "schemas").is_dir() else _HERE.parents[1]
SCHEMA = ROOT / "schemas" / "repository-truth-packet.schema.json"

RESOURCE_LIMIT_VERSION = "repository-fingerprint-limits-v1"
SIZE_LIMIT = int(os.environ.get("STATEWORK_GIT_OUTPUT_LIMIT", 4 * 1024 * 1024))
MAX_UNTRACKED_ENTRIES = int(os.environ.get("STATEWORK_MAX_UNTRACKED_ENTRIES", 10_000))
MAX_UNTRACKED_FILE_BYTES = int(os.environ.get("STATEWORK_MAX_UNTRACKED_FILE_BYTES", 16 * 1024 * 1024))
MAX_UNTRACKED_TOTAL_BYTES = int(os.environ.get("STATEWORK_MAX_UNTRACKED_TOTAL_BYTES", 64 * 1024 * 1024))


class GitError(RuntimeError):
    pass


class ResourceLimitError(GitError):
    """Fingerprinting could not establish complete truth within its budget."""


def _bounded_subprocess(command: list[str], *, output_limit: int,
                        timeout: int) -> tuple[int, bytes, bytes]:
    """Drain stdout/stderr concurrently with a hard output budget."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    selector = selectors.DefaultSelector()
    assert process.stdout is not None and process.stderr is not None
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    output = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.wait()
                raise GitError(f"git {' '.join(command[3:])} timed out")
            for key, _ in selector.select(min(remaining, 0.25)):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                bucket = output[key.data]
                bucket.extend(chunk)
                if len(bucket) > output_limit:
                    process.kill()
                    process.wait()
                    raise ResourceLimitError(
                        f"git output exceeds {output_limit} byte limit")
        return process.wait(), bytes(output["stdout"]), bytes(output["stderr"])
    finally:
        selector.close()


def git(repo: Path, *args: str, check: bool = True, timeout: int = 30) -> str:
    command = ["git", "-C", str(repo), *args]
    code, stdout, stderr = _bounded_subprocess(command, output_limit=SIZE_LIMIT,
                                               timeout=timeout)
    if check and code != 0:
        raise GitError(f"git {' '.join(args)} failed (exit {code}): "
                       f"{stderr.decode('utf-8', 'replace').strip()[:300]}")
    return stdout.decode("utf-8", "replace")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bounded_text(text: str) -> str:
    if len(text.encode("utf-8")) > SIZE_LIMIT:
        raise GitError("git output exceeds fingerprint size limit")
    return text


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def repo_identity(repo: Path) -> str:
    """Canonical repository identity: resolved git top-level path hashed with
    the origin remote URL when present. Compared directly, never by path
    prefix."""
    top = git(repo, "rev-parse", "--show-toplevel").strip()
    remote = ""
    try:
        remote = git(repo, "config", "--get", "remote.origin.url").strip()
    except GitError:
        remote = ""
    return _sha256(f"{top}\n{remote}".encode("utf-8"))


def worktree_fingerprint(repo: Path) -> str:
    """Fingerprint actual repository state: HEAD, index diff, working-tree
    diff, and the mode/content hash of every untracked path."""
    parts: list[str] = []
    head = git(repo, "rev-parse", "HEAD").strip()
    parts.append(f"HEAD={head}")
    for label, args in [
        ("index", ["diff", "--cached", "--no-ext-diff"]),
        ("worktree", ["diff", "--no-ext-diff"]),
        ("untracked", ["ls-files", "--others", "--exclude-standard", "-z"]),
    ]:
        out = git(repo, *args)
        if label == "untracked":
            entries: list[Dict[str, Any]] = []
            if len(out.encode("utf-8")) > SIZE_LIMIT:
                raise ResourceLimitError("untracked inventory exceeds output limit")
            total_file_bytes = 0
            for item in out.split("\0"):
                if not item:
                    continue
                if len(entries) >= MAX_UNTRACKED_ENTRIES:
                    raise ResourceLimitError("untracked entry count exceeds configured limit")
                relative = Path(item)
                absolute = repo / relative
                try:
                    if absolute.is_symlink():
                        entry: Dict[str, Any] = {
                            "path": relative.as_posix(), "mode": "symlink",
                            "content_hash": _sha256(str(absolute.readlink()).encode("utf-8")),
                        }
                    elif absolute.is_file():
                        file_size = absolute.stat().st_size
                        if file_size > MAX_UNTRACKED_FILE_BYTES:
                            raise ResourceLimitError(
                                f"untracked file exceeds per-file limit: {relative}")
                        total_file_bytes += file_size
                        if total_file_bytes > MAX_UNTRACKED_TOTAL_BYTES:
                            raise ResourceLimitError("untracked file bytes exceed cumulative limit")
                        digest = hashlib.sha256()
                        with absolute.open("rb") as source:
                            while chunk := source.read(1024 * 1024):
                                digest.update(chunk)
                        entry = {
                            "path": relative.as_posix(), "mode": "file",
                            "content_hash": digest.hexdigest(),
                        }
                    else:
                        entry = {"path": relative.as_posix(), "mode": "other"}
                except OSError as exc:
                    raise GitError(
                        f"cannot fingerprint untracked path {relative}: {exc}") from exc
                entries.append(entry)
            value = _sha256(_stable_json(entries).encode("utf-8"))
        else:
            value = _sha256(_bounded_text(out).encode("utf-8"))
        parts.append(f"{label}={value}")
    return _sha256("\n".join(parts).encode("utf-8"))


def active_worktrees(repo: Path) -> str:
    """Hash canonical worktree records so path/HEAD/branch stay related."""
    text = git(repo, "worktree", "list", "--porcelain")
    records: list[Dict[str, str]] = []
    record: Dict[str, str] = {}
    for line in _bounded_text(text).splitlines():
        key, separator, value = line.partition(" ")
        if key == "worktree":
            if record:
                records.append(record)
            record = {"path": value}
        elif record is not None:
            record[key] = value
    if record:
        records.append(record)
    records.sort(key=lambda item: item.get("path", ""))
    return _sha256(_stable_json(records).encode("utf-8"))


def remote_fingerprint(repo: Path, remote: str = "origin") -> str | None:
    """Remote state. Unreachable remote -> None (truth unknown), which the
    caller treats as fail-closed for operations depending on remote state."""
    code, stdout, _stderr = _bounded_subprocess(
        ["git", "-C", str(repo), "ls-remote", "--exit-code", remote],
        output_limit=SIZE_LIMIT, timeout=30)
    if code != 0:
        return None
    return _sha256(_bounded_text(stdout.decode("utf-8", "replace")).encode("utf-8"))


def load_packet_schema() -> "Draft202012Validator":
    import jsonschema
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    registry = Registry()
    for reg_schema_path in sorted((ROOT / "schemas").glob("*.json")):
        reg_schema = json.loads(reg_schema_path.read_text(encoding="utf-8"))
        uri = reg_schema.get("$id")
        if uri:
            registry = registry.with_resource(uri, Resource.from_contents(reg_schema))
    return Draft202012Validator(
        schema, registry=registry, format_checker=FormatChecker())


def validate_repository_truth_packet(packet: dict, repo: Path) -> dict:
    """Compare packet fields against current repo state. Returns
    valid, invalid_fields, required_reobservations."""
    # schema first — freshness comparisons on a malformed packet are invalid
    validator = load_packet_schema()
    schema_errors = sorted(validator.iter_errors(packet), key=lambda e: list(e.path))
    if schema_errors:
        return {
            "valid": False,
            "schema_errors": [e.message for e in schema_errors],
            "invalid_fields": [],
            "required_reobservations": [],
        }

    payload = packet.get("payload", {})
    freshness = payload.get("freshness", {})
    invalid_fields: list[str] = []
    required: list[str] = []

    # repo identity: canonical direct comparison
    tracked_identity = freshness.get("repo_identity")
    try:
        cur_identity = repo_identity(repo)
        if not tracked_identity:
            invalid_fields.append("repo_identity")
            required.append("repo_identity")
        elif tracked_identity != cur_identity:
            invalid_fields.append("repo_identity")
            required.append("repo_identity")
    except GitError as exc:
        invalid_fields.append("repo_identity")
        required.append("repo_identity")
        required.append(f"repo_identity unavailable: {exc}")

    # observed head
    tracked_head = freshness.get("observed_head")
    try:
        cur_head = git(repo, "rev-parse", "HEAD").strip()
        if not tracked_head or tracked_head != cur_head:
            invalid_fields.append("observed_head")
            required.append("observed_head")
    except GitError as exc:
        invalid_fields.append("observed_head")
        required.append(f"observed_head unavailable: {exc}")

    # working tree fingerprint (real state; git failure fails closed)
    wt = freshness.get("working_tree_fingerprint")
    try:
        cur_wt = worktree_fingerprint(repo)
        if wt != cur_wt:
            invalid_fields.append("working_tree_fingerprint")
            required.append("working_tree_fingerprint")
    except ResourceLimitError as exc:
        return {
            "valid": False, "truth_unknown": "resource_limit",
            "resource_limit": RESOURCE_LIMIT_VERSION,
            "resource_limit_detail": str(exc), "invalid_fields": [],
            "required_reobservations": ["working_tree_fingerprint"],
        }
    except GitError as exc:
        invalid_fields.append("working_tree_fingerprint")
        required.append(f"working_tree_fingerprint unavailable: {exc}")

    # active worktrees
    wtree = freshness.get("active_worktree_snapshot")
    try:
        cur_wtree = active_worktrees(repo)
        if wtree != cur_wtree:
            invalid_fields.append("active_worktree_snapshot")
            required.append("active_worktree_snapshot")
    except GitError as exc:
        invalid_fields.append("active_worktree_snapshot")
        required.append(f"active_worktree_snapshot unavailable: {exc}")

    # remote state: fail-closed — packet has a remote fingerprint and the
    # current lookup is unavailable => remote truth is unknown, not valid
    remote = freshness.get("remote_state_fingerprint")
    if remote is not None:
        cur_remote = remote_fingerprint(repo)
        if cur_remote is None:
            invalid_fields.append("remote_state_fingerprint")
            required.append("remote_state_fingerprint (remote lookup unavailable; truth unknown)")
        elif remote != cur_remote:
            invalid_fields.append("remote_state_fingerprint")
            required.append("remote_state_fingerprint")

    return {
        "valid": not invalid_fields,
        "resource_limit": RESOURCE_LIMIT_VERSION,
        "invalid_fields": invalid_fields,
        "required_reobservations": sorted(set(required)),
        "triggered_invalidations": sorted(set(invalid_fields)),
        "informational_invalidation_rules": [
            condition for condition in freshness.get("invalidation_conditions", [])
            if condition
        ],
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    packet = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    repo = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path.cwd().resolve()
    result = validate_repository_truth_packet(packet, repo)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
