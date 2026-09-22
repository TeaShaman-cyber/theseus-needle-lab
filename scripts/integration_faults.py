#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_TAXONOMY = ROOT / "config" / "integration-fault-taxonomy.json"
RECEIPT_SCHEMA = "needle-integration-fault-receipt-v1"
CHECKPOINT_SCHEMA = "needle-execution-checkpoint-v1"
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA64_RE = re.compile(r"^[0-9a-f]{64}$")
EVIDENCE_STATUSES = {"VERIFIED", "PARTIAL", "UNAVAILABLE"}
CLASSIFICATION_SOURCES = {"CHECKPOINT_DERIVED", "EXPLICIT_OBSERVATION"}
FORBIDDEN_MAPPED_STATES = {"PASS", "NO_CALL", "ACCEPTED", "REJECTED"}


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_taxonomy(path: pathlib.Path = DEFAULT_TAXONOMY) -> dict[str, Any]:
    taxonomy = load_json(path)
    if taxonomy.get("schema_version") != "needle-integration-fault-taxonomy-v1":
        raise ValueError("unsupported taxonomy schema")

    allowed_states = taxonomy.get("allowed_mapped_states")
    if not isinstance(allowed_states, list) or not allowed_states:
        raise ValueError("taxonomy mapped-state list is missing")
    if set(allowed_states) & FORBIDDEN_MAPPED_STATES:
        raise ValueError("taxonomy contains forbidden success/outcome states")

    classes = taxonomy.get("classes")
    if not isinstance(classes, dict) or not classes:
        raise ValueError("taxonomy classes are missing")

    for name, spec in classes.items():
        if not isinstance(name, str) or not name:
            raise ValueError("invalid fault class name")
        if spec.get("kind") not in {"infrastructure_fault", "bounded_witness"}:
            raise ValueError(f"invalid kind for {name}")
        mapped_state = spec.get("mapped_state")
        if mapped_state not in allowed_states or mapped_state in FORBIDDEN_MAPPED_STATES:
            raise ValueError(f"invalid mapped state for {name}")
        statuses = spec.get("allowed_evidence_status")
        if (
            not isinstance(statuses, list)
            or not statuses
            or not set(statuses).issubset(EVIDENCE_STATUSES)
        ):
            raise ValueError(f"invalid evidence statuses for {name}")
        required = spec.get("required_observation_fields")
        if not isinstance(required, list):
            raise ValueError(f"invalid required fields for {name}")
        if not isinstance(spec.get("requires_checkpoint"), bool):
            raise ValueError(f"invalid checkpoint requirement for {name}")
        if spec["kind"] == "bounded_witness" and statuses != ["VERIFIED"]:
            raise ValueError(f"bounded witness must require VERIFIED evidence: {name}")
    return taxonomy


def _validate_checkpoint_projection(checkpoint: dict[str, Any]) -> None:
    if checkpoint.get("schema_version") != CHECKPOINT_SCHEMA:
        raise ValueError("unsupported execution checkpoint schema")
    identity = checkpoint.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("execution checkpoint identity is missing")
    for key in ("experiment_sha", "launcher_sha", "run_id", "run_attempt", "stage", "unit"):
        if key not in identity:
            raise ValueError(f"execution checkpoint identity missing {key}")
    if not SHA40_RE.fullmatch(str(identity["experiment_sha"])):
        raise ValueError("invalid experiment SHA")
    if not SHA40_RE.fullmatch(str(identity["launcher_sha"])):
        raise ValueError("invalid launcher SHA")
    if (
        not isinstance(identity["run_attempt"], int)
        or isinstance(identity["run_attempt"], bool)
        or identity["run_attempt"] < 1
    ):
        raise ValueError("invalid run attempt")
    if checkpoint.get("execution_status") not in {"RUNNING", "SUCCEEDED", "FAILED"}:
        raise ValueError("invalid execution status")
    if checkpoint.get("lifecycle_state") not in {"EXECUTING", "ARTIFACT_PROVENANCE"}:
        raise ValueError("invalid execution lifecycle state")
    if checkpoint.get("artifact_scan_status") not in {
        "NOT_STARTED",
        "IN_PROGRESS",
        "COMPLETE",
        "PARTIAL",
    }:
        raise ValueError("invalid artifact scan status")
    if not isinstance(checkpoint.get("artifacts"), list):
        raise ValueError("checkpoint artifacts must be a list")


def classify_checkpoint(checkpoint: dict[str, Any]) -> dict[str, Any] | None:
    _validate_checkpoint_projection(checkpoint)
    identity = checkpoint["identity"]
    surface = str(identity["stage"])
    execution_status = checkpoint["execution_status"]
    scan_status = checkpoint["artifact_scan_status"]

    if execution_status == "RUNNING":
        return {
            "fault_class": "EXECUTION_AMBIGUOUS",
            "evidence_status": "PARTIAL",
            "classification_source": "CHECKPOINT_DERIVED",
            "observed_surface": surface,
            "metric_or_check": "execution_status",
            "observed_value": "RUNNING",
            "expected_or_reference_value": "SUCCEEDED_OR_FAILED",
        }

    if execution_status == "FAILED":
        signal = checkpoint.get("command_signal")
        if isinstance(signal, int) and not isinstance(signal, bool) and signal > 0:
            return {
                "fault_class": "EXECUTION_INTERRUPTED",
                "evidence_status": "VERIFIED",
                "classification_source": "CHECKPOINT_DERIVED",
                "observed_surface": surface,
                "metric_or_check": "command_signal",
                "observed_value": signal,
                "expected_or_reference_value": 0,
            }
        return {
            "fault_class": "EXECUTION_FAILED",
            "evidence_status": "VERIFIED",
            "classification_source": "CHECKPOINT_DERIVED",
            "observed_surface": surface,
            "metric_or_check": "command_exit_code",
            "observed_value": checkpoint.get("command_exit_code"),
            "expected_or_reference_value": 0,
        }

    if scan_status in {"PARTIAL", "IN_PROGRESS", "NOT_STARTED"}:
        return {
            "fault_class": "ARTIFACT_PROVENANCE_INCOMPLETE",
            "evidence_status": "PARTIAL",
            "classification_source": "CHECKPOINT_DERIVED",
            "observed_surface": surface,
            "metric_or_check": "artifact_scan_status",
            "observed_value": scan_status,
            "expected_or_reference_value": "COMPLETE",
        }

    return None


def _required_observation_fields(
    observation: dict[str, Any],
    class_spec: dict[str, Any],
) -> None:
    for field in class_spec["required_observation_fields"]:
        if field not in observation or observation[field] is None:
            raise ValueError(f"missing required observation field: {field}")


def _checkpoint_projection(checkpoint: dict[str, Any]) -> dict[str, Any]:
    _validate_checkpoint_projection(checkpoint)
    return {
        "identity": dict(checkpoint["identity"]),
        "execution": {
            "execution_status": checkpoint["execution_status"],
            "lifecycle_state": checkpoint["lifecycle_state"],
            "artifact_scan_status": checkpoint["artifact_scan_status"],
            "command_exit_code": checkpoint.get("command_exit_code"),
            "command_signal": checkpoint.get("command_signal"),
        },
        "artifacts": list(checkpoint["artifacts"]),
    }


def build_receipt(
    observation: dict[str, Any],
    checkpoint: dict[str, Any] | None = None,
    *,
    checkpoint_sha256: str | None = None,
    taxonomy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    taxonomy = taxonomy or load_taxonomy()
    fault_class = observation.get("fault_class")
    class_spec = taxonomy["classes"].get(fault_class)
    if class_spec is None:
        raise ValueError("unknown fault class")

    evidence_status = observation.get("evidence_status")
    if evidence_status not in class_spec["allowed_evidence_status"]:
        raise ValueError("evidence status is not allowed for fault class")
    _required_observation_fields(observation, class_spec)

    source = observation.get("classification_source", "EXPLICIT_OBSERVATION")
    if source not in CLASSIFICATION_SOURCES:
        raise ValueError("invalid classification source")

    if class_spec["requires_checkpoint"]:
        if checkpoint is None:
            raise ValueError("fault class requires execution checkpoint")
        if not checkpoint_sha256 or not SHA64_RE.fullmatch(checkpoint_sha256):
            raise ValueError("fault class requires checkpoint SHA-256")
        projection = _checkpoint_projection(checkpoint)
    else:
        projection = {"identity": None, "execution": None, "artifacts": []}

    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "taxonomy_version": taxonomy["schema_version"],
        "fault_class": fault_class,
        "fault_kind": class_spec["kind"],
        "mapped_state": class_spec["mapped_state"],
        "evidence_status": evidence_status,
        "classification_source": source,
        "observed_surface": observation["observed_surface"],
        "execution_checkpoint_sha256": checkpoint_sha256,
        **projection,
    }
    for field in (
        "reference_surface",
        "candidate_surface",
        "metric_or_check",
        "observed_value",
        "expected_or_reference_value",
        "notes",
    ):
        if field in observation:
            receipt[field] = observation[field]

    validate_receipt(receipt, taxonomy)
    return receipt


def validate_receipt(
    receipt: dict[str, Any],
    taxonomy: dict[str, Any] | None = None,
) -> None:
    taxonomy = taxonomy or load_taxonomy()
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise ValueError("unsupported integration fault receipt schema")
    if receipt.get("taxonomy_version") != taxonomy["schema_version"]:
        raise ValueError("fault taxonomy version mismatch")
    if "scientific_outcome" in receipt:
        raise ValueError("fault receipt cannot decide scientific outcome")

    fault_class = receipt.get("fault_class")
    class_spec = taxonomy["classes"].get(fault_class)
    if class_spec is None:
        raise ValueError("unknown fault class in receipt")
    if receipt.get("fault_kind") != class_spec["kind"]:
        raise ValueError("fault kind mismatch")
    if receipt.get("mapped_state") != class_spec["mapped_state"]:
        raise ValueError("fault mapped state mismatch")
    if receipt.get("mapped_state") in FORBIDDEN_MAPPED_STATES:
        raise ValueError("forbidden success/outcome mapped state")
    if receipt.get("evidence_status") not in class_spec["allowed_evidence_status"]:
        raise ValueError("invalid receipt evidence status")
    if receipt.get("classification_source") not in CLASSIFICATION_SOURCES:
        raise ValueError("invalid receipt classification source")
    _required_observation_fields(receipt, class_spec)

    if class_spec["requires_checkpoint"]:
        digest = receipt.get("execution_checkpoint_sha256")
        if not isinstance(digest, str) or not SHA64_RE.fullmatch(digest):
            raise ValueError("invalid execution checkpoint SHA-256")
        projection = {
            "schema_version": CHECKPOINT_SCHEMA,
            "identity": receipt.get("identity"),
            **(receipt.get("execution") or {}),
            "artifacts": receipt.get("artifacts"),
        }
        _validate_checkpoint_projection(projection)


def validate_receipt_against_checkpoint(
    receipt: dict[str, Any],
    checkpoint: dict[str, Any],
    checkpoint_sha256: str,
    taxonomy: dict[str, Any] | None = None,
) -> None:
    taxonomy = taxonomy or load_taxonomy()
    validate_receipt(receipt, taxonomy)
    if receipt.get("execution_checkpoint_sha256") != checkpoint_sha256:
        raise ValueError("receipt checkpoint digest mismatch")
    projection = _checkpoint_projection(checkpoint)
    if receipt.get("identity") != projection["identity"]:
        raise ValueError("receipt checkpoint identity mismatch")
    if receipt.get("execution") != projection["execution"]:
        raise ValueError("receipt checkpoint execution mismatch")
    if receipt.get("artifacts") != projection["artifacts"]:
        raise ValueError("receipt checkpoint artifact mismatch")


def _write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _checkpoint_from_path(path: pathlib.Path) -> tuple[dict[str, Any], str]:
    checkpoint = load_json(path)
    return checkpoint, sha256_file(path)


def _classify_checkpoint_command(args: argparse.Namespace) -> int:
    taxonomy = load_taxonomy(args.taxonomy)
    checkpoint, digest = _checkpoint_from_path(args.checkpoint)
    observation = classify_checkpoint(checkpoint)
    if observation is None:
        raise SystemExit("NO_FAULT_DETECTED")
    receipt = build_receipt(
        observation,
        checkpoint,
        checkpoint_sha256=digest,
        taxonomy=taxonomy,
    )
    _write_json(args.output, receipt)
    print(
        "INTEGRATION_FAULT_RECEIPT=PASS "
        f"CLASS={receipt['fault_class']} "
        f"STATE={receipt['mapped_state']}"
    )
    return 0


def _build_command(args: argparse.Namespace) -> int:
    taxonomy = load_taxonomy(args.taxonomy)
    observation = load_json(args.observation)
    checkpoint = None
    digest = None
    if args.checkpoint is not None:
        checkpoint, digest = _checkpoint_from_path(args.checkpoint)
    receipt = build_receipt(
        observation,
        checkpoint,
        checkpoint_sha256=digest,
        taxonomy=taxonomy,
    )
    _write_json(args.output, receipt)
    print(
        "INTEGRATION_FAULT_RECEIPT=PASS "
        f"CLASS={receipt['fault_class']} "
        f"STATE={receipt['mapped_state']}"
    )
    return 0


def _validate_command(args: argparse.Namespace) -> int:
    taxonomy = load_taxonomy(args.taxonomy)
    receipt = load_json(args.receipt)
    if args.checkpoint is None:
        validate_receipt(receipt, taxonomy)
    else:
        checkpoint, digest = _checkpoint_from_path(args.checkpoint)
        validate_receipt_against_checkpoint(receipt, checkpoint, digest, taxonomy)
    print(
        "INTEGRATION_FAULT_RECEIPT_VALID=PASS "
        f"CLASS={receipt['fault_class']} "
        f"STATE={receipt['mapped_state']}"
    )
    return 0


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Needle integration fault taxonomy and receipt helper.")
    parser.add_argument("--taxonomy", type=pathlib.Path, default=DEFAULT_TAXONOMY)
    sub = parser.add_subparsers(dest="command", required=True)

    classify = sub.add_parser("classify-checkpoint")
    classify.add_argument("--checkpoint", type=pathlib.Path, required=True)
    classify.add_argument("--output", type=pathlib.Path, required=True)
    classify.set_defaults(func=_classify_checkpoint_command)

    build = sub.add_parser("build")
    build.add_argument("--observation", type=pathlib.Path, required=True)
    build.add_argument("--checkpoint", type=pathlib.Path)
    build.add_argument("--output", type=pathlib.Path, required=True)
    build.set_defaults(func=_build_command)

    validate = sub.add_parser("validate-receipt")
    validate.add_argument("--receipt", type=pathlib.Path, required=True)
    validate.add_argument("--checkpoint", type=pathlib.Path)
    validate.set_defaults(func=_validate_command)
    return parser


def main() -> int:
    args = parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
