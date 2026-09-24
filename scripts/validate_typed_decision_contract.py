#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts" / "typed-decision" / "v1.schema.json"
FIXTURES_PATH = ROOT / "contracts" / "typed-decision" / "fixtures.v1.jsonl"

REQUIRED = {
    "schema",
    "task",
    "outcome",
    "decision",
    "probe",
    "signal",
    "error",
    "advisory_confidence",
    "evidence_refs",
    "currentness_refs",
    "escalation_reason",
    "authority_required",
    "extensions",
}
TASKS = {"EVIDENCE_ROUTING", "DRIFT_SENTINEL"}
OUTCOMES = {"DECISION", "NO_CALL", "SIGNAL", "NO_SIGNAL", "ERROR"}
DECISIONS = {"PROBE", "READY", "UNKNOWN"}
ESCALATIONS = {
    "NONE",
    "CURRENTNESS_REQUIRED",
    "CONFLICTING_EVIDENCE",
    "INSUFFICIENT_EVIDENCE",
    "NO_SAFE_PROBE",
    "OUT_OF_SCOPE",
    "DRIFT_SIGNAL",
    "LEGACY_UNSPECIFIED",
    "ERROR",
}
PROBE_ESCALATIONS = {
    "CURRENTNESS_REQUIRED",
    "CONFLICTING_EVIDENCE",
    "INSUFFICIENT_EVIDENCE",
    "LEGACY_UNSPECIFIED",
}
UNKNOWN_ESCALATIONS = {
    "CONFLICTING_EVIDENCE",
    "INSUFFICIENT_EVIDENCE",
    "NO_SAFE_PROBE",
    "LEGACY_UNSPECIFIED",
}


def fail(message: str) -> None:
    raise ValueError(message)


def validate_refs(value: Any, label: str) -> None:
    if not isinstance(value, list):
        fail(f"{label} must be a list")
    if any(not isinstance(item, str) or not item for item in value):
        fail(f"{label} entries must be non-empty strings")
    if len(value) != len(set(value)):
        fail(f"{label} entries must be unique")


def validate_confidence(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"kind", "value", "calibrated"}:
        fail("advisory_confidence shape invalid")
    kind = value["kind"]
    score = value["value"]
    calibrated = value["calibrated"]
    if not isinstance(calibrated, bool):
        fail("advisory_confidence.calibrated must be boolean")
    if kind == "UNAVAILABLE":
        if score is not None or calibrated:
            fail("UNAVAILABLE confidence requires value=null and calibrated=false")
        return
    if kind not in {"MODEL_REPORTED", "CALIBRATED_POSTHOC"}:
        fail("advisory_confidence.kind invalid")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        fail("numeric confidence required")
    score = float(score)
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        fail("confidence must be finite in [0,1]")
    if kind == "MODEL_REPORTED" and calibrated:
        fail("MODEL_REPORTED confidence must not claim calibration")
    if kind == "CALIBRATED_POSTHOC" and not calibrated:
        fail("CALIBRATED_POSTHOC requires calibrated=true")


def validate_probe(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"kind", "route_target"}:
        fail("probe shape invalid")
    if not isinstance(value["kind"], str) or not value["kind"]:
        fail("probe.kind invalid")
    target = value["route_target"]
    if target is not None and (not isinstance(target, str) or not target):
        fail("probe.route_target invalid")


def validate_signal(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"name", "payload"}:
        fail("signal shape invalid")
    if not isinstance(value["name"], str) or not value["name"]:
        fail("signal.name invalid")
    if not isinstance(value["payload"], dict):
        fail("signal.payload must be an object")


def validate_error(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"code", "phase", "message"}:
        fail("error shape invalid")
    for key in ("code", "phase"):
        if not isinstance(value[key], str) or not value[key]:
            fail(f"error.{key} invalid")
    if value["message"] is not None and not isinstance(value["message"], str):
        fail("error.message invalid")


def validate_envelope(value: Any) -> None:
    if not isinstance(value, dict):
        fail("envelope must be an object")
    if set(value) != REQUIRED:
        fail("envelope keys do not match v1 contract")
    if value["schema"] != "theseus.typed-decision.v1":
        fail("schema version mismatch")
    if value["task"] not in TASKS:
        fail("task invalid")
    if value["outcome"] not in OUTCOMES:
        fail("outcome invalid")
    if value["decision"] is not None and value["decision"] not in DECISIONS:
        fail("decision invalid")
    if value["escalation_reason"] not in ESCALATIONS:
        fail("escalation_reason invalid")
    if not isinstance(value["authority_required"], bool):
        fail("authority_required must be boolean")
    if not isinstance(value["extensions"], dict):
        fail("extensions must be an object")
    validate_refs(value["evidence_refs"], "evidence_refs")
    validate_refs(value["currentness_refs"], "currentness_refs")
    validate_confidence(value["advisory_confidence"])

    outcome = value["outcome"]
    decision = value["decision"]
    probe = value["probe"]
    signal = value["signal"]
    error = value["error"]
    escalation = value["escalation_reason"]

    if outcome == "DECISION":
        if decision not in DECISIONS or signal is not None or error is not None:
            fail("DECISION envelope invalid")
        if decision == "PROBE":
            validate_probe(probe)
            if escalation not in PROBE_ESCALATIONS:
                fail("PROBE escalation invalid")
        else:
            if probe is not None:
                fail(f"{decision} must not carry a probe")
            if decision == "READY" and escalation != "NONE":
                fail("READY escalation must be NONE")
            if decision == "UNKNOWN" and escalation not in UNKNOWN_ESCALATIONS:
                fail("UNKNOWN escalation invalid")
        return

    if decision is not None or probe is not None:
        fail(f"{outcome} must not carry decision/probe")

    if outcome == "NO_CALL":
        if value["task"] != "EVIDENCE_ROUTING":
            fail("NO_CALL is reserved for routing applicability")
        if signal is not None or error is not None or escalation != "OUT_OF_SCOPE":
            fail("NO_CALL envelope invalid")
        return

    if outcome == "SIGNAL":
        if value["task"] != "DRIFT_SENTINEL" or error is not None:
            fail("SIGNAL task/error invalid")
        validate_signal(signal)
        if escalation != "DRIFT_SIGNAL":
            fail("SIGNAL escalation invalid")
        return

    if outcome == "NO_SIGNAL":
        if value["task"] != "DRIFT_SENTINEL":
            fail("NO_SIGNAL is reserved for drift sentinel")
        if signal is not None or error is not None or escalation != "NONE":
            fail("NO_SIGNAL envelope invalid")
        return

    if outcome == "ERROR":
        if signal is not None or escalation != "ERROR":
            fail("ERROR envelope invalid")
        validate_error(error)
        return

    fail("unreachable outcome")


def load_fixtures(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            fail("fixture row must be an object")
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", default=str(FIXTURES_PATH))
    args = parser.parse_args()

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        fail("unexpected JSON Schema draft")
    rows = load_fixtures(Path(args.fixtures))
    seen = set()
    for row in rows:
        if set(row) != {"case_id", "family", "expected"}:
            fail("fixture row keys invalid")
        case_id = row["case_id"]
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            fail("invalid or duplicate fixture case_id")
        seen.add(case_id)
        if not isinstance(row["family"], str) or not row["family"]:
            fail("fixture family invalid")
        validate_envelope(row["expected"])
    print(f"TYPED_DECISION_CONTRACT_PASS fixtures={len(rows)}")


if __name__ == "__main__":
    main()
