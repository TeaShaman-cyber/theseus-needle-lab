#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from typing import Any

SCHEMA_VERSION = "needle-execution-checkpoint-v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EXECUTION_STATUSES = {"RUNNING", "SUCCEEDED", "FAILED"}
LIFECYCLE_STATES = {"EXECUTING", "ARTIFACT_PROVENANCE"}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def append_heartbeat(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def validate_sha(value: str, name: str) -> None:
    if not SHA_RE.fullmatch(value):
        raise SystemExit(f"INVALID_{name.upper()}")


def _path_is_hidden(path: pathlib.Path, root: pathlib.Path) -> bool:
    relative = path.relative_to(root.parent if root.is_file() else root)
    return any(part.startswith(".") for part in relative.parts)


def _validated_artifact_roots(roots: list[str], cwd: pathlib.Path) -> list[pathlib.Path]:
    workspace = cwd.resolve()
    validated: list[pathlib.Path] = []
    for raw_root in roots:
        candidate = cwd / raw_root
        try:
            candidate.resolve(strict=False).relative_to(workspace)
        except ValueError as exc:
            raise SystemExit("ARTIFACT_ROOT_OUTSIDE_WORKSPACE") from exc
        validated.append(candidate)
    return validated


def snapshot_artifacts(roots: list[pathlib.Path], cwd: pathlib.Path) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    workspace = cwd.resolve()
    seen: set[str] = set()

    for root in roots:
        if root.is_symlink() or not root.exists():
            continue

        candidates = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in candidates:
            if path.is_symlink() or not path.is_file() or _path_is_hidden(path, root):
                continue
            try:
                resolved = path.resolve().relative_to(workspace)
            except ValueError:
                # Match upload semantics without allowing an artifact symlink or
                # other escaped path to overwrite the wrapped command's status.
                continue

            rel = resolved.as_posix()
            if rel in seen:
                continue
            seen.add(rel)
            found.append(
                {
                    "path": rel,
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )

    found.sort(key=lambda item: item["path"])
    return found


def heartbeat_record(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": state["schema_version"],
        "experiment_sha": state["identity"]["experiment_sha"],
        "launcher_sha": state["identity"]["launcher_sha"],
        "run_id": state["identity"]["run_id"],
        "run_attempt": state["identity"]["run_attempt"],
        "stage": state["identity"]["stage"],
        "unit": state["identity"]["unit"],
        "sequence": state["heartbeat_sequence"],
        "timestamp": state["updated_at"],
        "execution_status": state["execution_status"],
        "lifecycle_state": state["lifecycle_state"],
    }


def run_command(args: argparse.Namespace) -> int:
    validate_sha(args.experiment_sha, "experiment_sha")
    validate_sha(args.launcher_sha, "launcher_sha")
    if args.heartbeat_seconds <= 0:
        raise SystemExit("INVALID_HEARTBEAT_INTERVAL")

    command = list(args.wrapped_command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("MISSING_COMMAND")

    checkpoint = pathlib.Path(args.checkpoint)
    heartbeat = pathlib.Path(args.heartbeat)
    cwd = pathlib.Path.cwd()
    artifact_roots = _validated_artifact_roots(args.artifact_root, cwd)
    now = utc_now()
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "identity": {
            "experiment_sha": args.experiment_sha,
            "launcher_sha": args.launcher_sha,
            "run_id": str(args.run_id),
            "run_attempt": int(args.run_attempt),
            "stage": args.stage,
            "unit": args.unit,
        },
        "lifecycle_state": "EXECUTING",
        "execution_status": "RUNNING",
        "started_at": now,
        "updated_at": now,
        "heartbeat_interval_seconds": args.heartbeat_seconds,
        "heartbeat_sequence": 0,
        "command_exit_code": None,
        "command_signal": None,
        "artifacts": [],
    }
    atomic_json(checkpoint, state)
    append_heartbeat(heartbeat, heartbeat_record(state))

    process = subprocess.Popen(command)
    while True:
        try:
            return_code = process.wait(timeout=args.heartbeat_seconds)
            break
        except subprocess.TimeoutExpired:
            state["heartbeat_sequence"] += 1
            state["updated_at"] = utc_now()
            atomic_json(checkpoint, state)
            append_heartbeat(heartbeat, heartbeat_record(state))

    artifacts = snapshot_artifacts(artifact_roots, cwd)
    state["heartbeat_sequence"] += 1
    state["updated_at"] = utc_now()
    state["ended_at"] = state["updated_at"]
    raw_return_code = int(return_code)
    if raw_return_code < 0:
        state["command_signal"] = -raw_return_code
        state["command_exit_code"] = 128 + state["command_signal"]
    else:
        state["command_exit_code"] = raw_return_code
    state["execution_status"] = "SUCCEEDED" if raw_return_code == 0 else "FAILED"
    state["artifacts"] = artifacts
    if artifacts:
        state["lifecycle_state"] = "ARTIFACT_PROVENANCE"
    atomic_json(checkpoint, state)
    append_heartbeat(heartbeat, heartbeat_record(state))
    print(
        "EXECUTION_TELEMETRY_STATUS="
        f"{state['execution_status']} "
        f"LIFECYCLE_STATE={state['lifecycle_state']} "
        f"ARTIFACTS={len(artifacts)}"
    )
    return int(state["command_exit_code"])


def load_checkpoint(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("INVALID_CHECKPOINT_JSON") from exc

    required = {
        "schema_version",
        "identity",
        "lifecycle_state",
        "execution_status",
        "started_at",
        "updated_at",
        "heartbeat_interval_seconds",
        "heartbeat_sequence",
        "command_exit_code",
        "command_signal",
        "artifacts",
    }
    if not required.issubset(value):
        raise SystemExit("CHECKPOINT_MISSING_FIELDS")
    if value["schema_version"] != SCHEMA_VERSION:
        raise SystemExit("CHECKPOINT_SCHEMA_MISMATCH")

    identity = value["identity"]
    for key in ("experiment_sha", "launcher_sha", "run_id", "run_attempt", "stage", "unit"):
        if key not in identity:
            raise SystemExit("CHECKPOINT_IDENTITY_MISSING")
    validate_sha(identity["experiment_sha"], "experiment_sha")
    validate_sha(identity["launcher_sha"], "launcher_sha")
    if value["execution_status"] not in EXECUTION_STATUSES:
        raise SystemExit("CHECKPOINT_EXECUTION_STATUS_INVALID")
    if value["lifecycle_state"] not in LIFECYCLE_STATES:
        raise SystemExit("CHECKPOINT_LIFECYCLE_STATE_INVALID")
    return value


def validate_checkpoint(args: argparse.Namespace) -> int:
    checkpoint_path = pathlib.Path(args.checkpoint)
    value = load_checkpoint(checkpoint_path)
    identity = value["identity"]

    expected = {
        "experiment_sha": args.expected_experiment_sha,
        "launcher_sha": args.expected_launcher_sha,
        "stage": args.expected_stage,
        "unit": args.expected_unit,
    }
    for key, wanted in expected.items():
        if wanted is not None and str(identity[key]) != str(wanted):
            raise SystemExit(f"CHECKPOINT_{key.upper()}_MISMATCH")

    if args.expected_execution_status and value["execution_status"] != args.expected_execution_status:
        raise SystemExit("CHECKPOINT_EXECUTION_STATUS_MISMATCH")
    if args.expected_lifecycle_state and value["lifecycle_state"] != args.expected_lifecycle_state:
        raise SystemExit("CHECKPOINT_LIFECYCLE_STATE_MISMATCH")

    root = pathlib.Path(args.root).resolve()
    for artifact in value["artifacts"]:
        path = (root / artifact["path"]).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise SystemExit("CHECKPOINT_ARTIFACT_OUTSIDE_ROOT") from exc
        if not path.is_file():
            raise SystemExit("CHECKPOINT_ARTIFACT_MISSING")
        if path.stat().st_size != int(artifact["bytes"]):
            raise SystemExit("CHECKPOINT_ARTIFACT_SIZE_MISMATCH")
        if sha256_file(path) != artifact["sha256"]:
            raise SystemExit("CHECKPOINT_ARTIFACT_HASH_MISMATCH")

    if args.heartbeat:
        heartbeat_path = pathlib.Path(args.heartbeat)
        try:
            lines = [
                json.loads(line)
                for line in heartbeat_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit("INVALID_HEARTBEAT_LOG") from exc
        if not lines:
            raise SystemExit("HEARTBEAT_LOG_EMPTY")

        sequences = [int(line["sequence"]) for line in lines]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise SystemExit("HEARTBEAT_SEQUENCE_INVALID")
        if sequences[-1] != int(value["heartbeat_sequence"]):
            raise SystemExit("HEARTBEAT_CHECKPOINT_DIVERGENCE")
        for line in lines:
            for key in ("experiment_sha", "launcher_sha", "run_id", "run_attempt", "stage", "unit"):
                if str(line[key]) != str(identity[key]):
                    raise SystemExit("HEARTBEAT_IDENTITY_MISMATCH")

    print(
        "EXECUTION_CHECKPOINT_VALID=PASS "
        f"STATUS={value['execution_status']} "
        f"LIFECYCLE_STATE={value['lifecycle_state']} "
        f"ARTIFACTS={len(value['artifacts'])}"
    )
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Bounded execution telemetry and recovery checkpoint helper.")
    sub = p.add_subparsers(dest="command_name", required=True)

    run = sub.add_parser("run")
    run.add_argument("--experiment-sha", required=True)
    run.add_argument("--launcher-sha", required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--run-attempt", type=int, required=True)
    run.add_argument("--stage", required=True)
    run.add_argument("--unit", default="global")
    run.add_argument("--heartbeat-seconds", type=float, default=300.0)
    run.add_argument("--checkpoint", default="telemetry/execution-checkpoint.json")
    run.add_argument("--heartbeat", default="telemetry/heartbeat.jsonl")
    run.add_argument("--artifact-root", action="append", default=[])
    run.add_argument("wrapped_command", nargs=argparse.REMAINDER)
    run.set_defaults(func=run_command)

    validate = sub.add_parser("validate")
    validate.add_argument("--checkpoint", required=True)
    validate.add_argument("--heartbeat")
    validate.add_argument("--root", default=".")
    validate.add_argument("--expected-experiment-sha")
    validate.add_argument("--expected-launcher-sha")
    validate.add_argument("--expected-stage")
    validate.add_argument("--expected-unit")
    validate.add_argument("--expected-execution-status", choices=sorted(EXECUTION_STATUSES))
    validate.add_argument("--expected-lifecycle-state", choices=sorted(LIFECYCLE_STATES))
    validate.set_defaults(func=validate_checkpoint)
    return p


def main() -> int:
    args = parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
