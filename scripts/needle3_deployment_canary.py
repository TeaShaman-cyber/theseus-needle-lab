#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import pathlib
import re
import sys
import time
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "experiments" / "needle3-deployment-canary" / "v1" / "manifest.json"
SURFACES = ("base_reference", "lora_reference", "built_cact")
DECISIONS = {"PROBE", "READY", "UNKNOWN"}
ALLOWED_PREDICTIONS = DECISIONS | {"NO_CALL", "INVALID"}
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA64_RE = re.compile(r"^[0-9a-f]{64}$")
RESULT_SCHEMA = "theseus.needle3.canary_surface_results.v1"
RECEIPT_SCHEMA = "theseus.needle3.deployment_canary_receipt.v1"


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def case_input_sha256(case: dict[str, Any]) -> str:
    return canonical_sha256({"query": case["query"], "tools": case["tools"]})


def verify_installed_package(manifest: dict[str, Any]) -> None:
    expected = manifest["upstream_snapshot"]["package_version"]
    try:
        observed = importlib.metadata.version("cactus-needle")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError("cactus-needle is not installed for real-surface execution") from exc
    if observed != expected:
        raise RuntimeError(
            f"installed cactus-needle version mismatch: expected {expected}, observed {observed}"
        )


def load_json(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("expected JSON object per line")
        rows.append(value)
    return rows


def write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: pathlib.Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def verify_file_identity(
    path: pathlib.Path,
    *,
    expected_sha256: str,
    expected_size: int,
    label: str,
) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} missing")
    size = path.stat().st_size
    if size != expected_size:
        raise ValueError(
            f"{label} size mismatch: expected {expected_size}, observed {size}"
        )
    digest = sha256_file(path)
    if digest != expected_sha256:
        raise ValueError(
            f"{label} SHA-256 mismatch: expected {expected_sha256}, observed {digest}"
        )
    return {
        "path": path.resolve().as_posix(),
        "size_bytes": size,
        "sha256": digest,
    }


def validate_manifest(manifest: dict[str, Any], manifest_path: pathlib.Path) -> list[dict[str, Any]]:
    if manifest.get("schema_version") != "theseus.needle3.deployment_canary_manifest.v1":
        raise ValueError("unsupported canary manifest schema")
    if manifest.get("surfaces") != list(SURFACES):
        raise ValueError("canary surfaces must use the exact frozen order")

    snapshot = manifest.get("upstream_snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("upstream snapshot missing")
    for key in ("source_commit", "release_tag_commit", "release_parent_source_commit"):
        if not SHA40_RE.fullmatch(str(snapshot.get(key, ""))):
            raise ValueError(f"invalid upstream {key}")
    if snapshot["release_parent_source_commit"] != snapshot["source_commit"]:
        raise ValueError("release tag parent does not match source commit")
    if not SHA64_RE.fullmatch(str(snapshot.get("wheel_sha256", ""))):
        raise ValueError("invalid package wheel SHA-256")

    assets = manifest.get("published_runtime_assets")
    if not isinstance(assets, dict):
        raise ValueError("published runtime assets missing")
    if assets.get("repository") != "Cactus-Compute/needle3":
        raise ValueError("unexpected published runtime asset repository")
    if not SHA40_RE.fullmatch(str(assets.get("repository_revision", ""))):
        raise ValueError("invalid published runtime repository revision")
    for key in ("base_checkpoint", "published_base_cact"):
        value = assets.get(key)
        if not isinstance(value, dict):
            raise ValueError(f"published runtime asset missing: {key}")
        if not isinstance(value.get("path"), str) or not value["path"]:
            raise ValueError(f"published runtime asset path missing: {key}")
        if not SHA64_RE.fullmatch(str(value.get("sha256", ""))):
            raise ValueError(f"published runtime asset SHA-256 invalid: {key}")
        if (
            not isinstance(value.get("size_bytes"), int)
            or isinstance(value["size_bytes"], bool)
            or value["size_bytes"] <= 0
        ):
            raise ValueError(f"published runtime asset size invalid: {key}")

    engine = assets.get("engine")
    if not isinstance(engine, dict):
        raise ValueError("published runtime engine metadata missing")
    expected_engine = {
        "version": "3.0.1",
        "platform_tag": "manylinux2014_x86_64",
        "wheel_path": "python/cactus_needle-3.0.1-py3-none-manylinux2014_x86_64.whl",
        "binary_member": "needle/libneedle3.so",
    }
    for key, expected_value in expected_engine.items():
        if engine.get(key) != expected_value:
            raise ValueError(f"published runtime engine metadata mismatch: {key}")
    for key in ("wheel_sha256", "binary_sha256"):
        if not SHA64_RE.fullmatch(str(engine.get(key, ""))):
            raise ValueError(f"published runtime engine digest invalid: {key}")
    for key in ("wheel_size_bytes", "binary_size_bytes"):
        if (
            not isinstance(engine.get(key), int)
            or isinstance(engine[key], bool)
            or engine[key] <= 0
        ):
            raise ValueError(f"published runtime engine size invalid: {key}")

    fixture = manifest.get("fixture")
    if not isinstance(fixture, dict):
        raise ValueError("fixture missing")
    cases_path = ROOT / fixture["path"]
    if sha256_file(cases_path) != fixture.get("sha256"):
        raise ValueError("fixture SHA-256 mismatch")
    cases = load_jsonl(cases_path)
    if len(cases) != fixture.get("rows"):
        raise ValueError("fixture row count mismatch")
    if len(cases) != 12:
        raise ValueError("canary geometry changed")

    ids = set()
    counts = collections.Counter()
    families = set()
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in ids:
            raise ValueError("invalid or duplicate case ID")
        ids.add(case_id)
        family = case.get("family_id")
        if not isinstance(family, str) or not family:
            raise ValueError("case family missing")
        families.add(family)
        expected = case.get("expected")
        if expected not in DECISIONS | {"NO_CALL"}:
            raise ValueError("invalid expected decision")
        category = case.get("category")
        if category not in {"positive", "negative"}:
            raise ValueError("invalid case category")
        if (expected == "NO_CALL") != (category == "negative"):
            raise ValueError("case category/expected mismatch")
        answers = case.get("answers")
        if not isinstance(answers, list):
            raise ValueError("answers must be a list")
        if expected == "NO_CALL" and answers:
            raise ValueError("negative case must have explicit empty answers")
        if expected != "NO_CALL" and len(answers) != 1:
            raise ValueError("positive case must have one expected call")
        if not isinstance(case.get("tools"), list) or not case["tools"]:
            raise ValueError("case tools missing")
        if not isinstance(case.get("query"), str) or not case["query"]:
            raise ValueError("case query missing")
        counts[expected] += 1

    if counts != collections.Counter({"NO_CALL": 6, "PROBE": 2, "READY": 2, "UNKNOWN": 2}):
        raise ValueError("canary decision geometry changed")
    if len(families) != 8:
        raise ValueError("canary family geometry changed")

    training = manifest.get("training_fixture")
    if not isinstance(training, dict):
        raise ValueError("training fixture missing")
    training_path = ROOT / training["path"]
    if sha256_file(training_path) != training.get("sha256"):
        raise ValueError("training fixture SHA-256 mismatch")
    training_rows = load_jsonl(training_path)
    if len(training_rows) != training.get("rows") or len(training_rows) != 48:
        raise ValueError("training fixture row count mismatch")

    training_counts = collections.Counter()
    training_ids = set()
    for row in training_rows:
        case_id = row.get("_canary_case_id")
        family_id = row.get("_canary_family_id")
        expected = row.get("_canary_expected")
        if not isinstance(case_id, str) or not case_id or case_id in training_ids:
            raise ValueError("invalid or duplicate training case ID")
        training_ids.add(case_id)
        if not isinstance(family_id, str) or not family_id:
            raise ValueError("training family missing")
        if expected not in DECISIONS | {"NO_CALL"}:
            raise ValueError("invalid training expected decision")
        if expected == "NO_CALL":
            if row.get("answers"):
                raise ValueError("training negative must have explicit empty answers")
        elif not isinstance(row.get("answers"), list) or len(row["answers"]) != 1:
            raise ValueError("training positive must have one expected call")
        if not isinstance(row.get("tools"), list) or not row["tools"]:
            raise ValueError("training tools missing")
        if not isinstance(row.get("query"), str) or not row["query"]:
            raise ValueError("training query missing")
        training_counts[expected] += 1

    expected_training_counts = collections.Counter(
        training.get("decision_counts", {})
    )
    if training_counts != expected_training_counts:
        raise ValueError("training decision geometry changed")
    if set(ids) & training_ids:
        raise ValueError("training/eval case leakage detected")

    config = training.get("training_config")
    if not isinstance(config, dict):
        raise ValueError("training config missing")
    expected_config = {
        "epochs": 2,
        "batch_size": 8,
        "lr": 0.0001,
        "lora_rank": 8,
        "lora_alpha": 16.0,
        "max_len": 512,
        "val_split": 0.0,
        "seed": 0,
    }
    if config != expected_config:
        raise ValueError("training config changed")

    thresholds = manifest.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError("thresholds missing")
    for key in (
        "deployment_pairwise_mismatch_count",
        "deployment_positive_correct_drop",
        "deployment_negative_no_call_drop",
        "applicability_route_call_drop",
        "applicability_negative_no_call_drop",
    ):
        value = thresholds.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"invalid threshold: {key}")
    dominant = thresholds.get("dominant_positive_decision_rate_max")
    if not isinstance(dominant, (int, float)) or isinstance(dominant, bool):
        raise ValueError("invalid dominant decision threshold")
    if not math.isfinite(float(dominant)) or not (0.0 < float(dominant) < 1.0):
        raise ValueError("dominant decision threshold must be finite in (0,1)")

    allowed = manifest.get("allowed_final_dispositions")
    expected_allowed = [
        "NO_CURRENT_SIGNAL",
        "DEPLOYMENT_DIVERGENCE_REPRODUCED",
        "APPLICABILITY_REGRESSION_REPRODUCED",
        "INCONCLUSIVE",
        "BLOCKED",
        "REPROBE_REQUIRED",
    ]
    if allowed != expected_allowed:
        raise ValueError("final disposition vocabulary changed")

    # Ensure the manifest passed to the CLI is the repository-bound fixture manifest,
    # not an arbitrary external file with matching shape.
    if manifest_path.resolve() != DEFAULT_MANIFEST.resolve():
        raise ValueError("canary manifest must be the repository-bound default")
    return cases


def classify_response(response: dict[str, Any]) -> str:
    calls = response.get("function_calls") or []
    response_type = response.get("type")
    if response_type == "invalid":
        return "INVALID"
    if response_type != "call":
        return "NO_CALL" if not calls else "INVALID"
    if not calls or len(calls) != 1:
        return "INVALID"
    call = calls[0]
    if not isinstance(call, dict) or call.get("name") != "route":
        return "INVALID"
    arguments = call.get("arguments") or {}
    if not isinstance(arguments, dict):
        return "INVALID"
    decision = arguments.get("decision")
    return decision if decision in DECISIONS else "INVALID"


def reference_text_to_response(text: str) -> dict[str, Any]:
    start = "<tool_call>"
    end = "</tool_call>"
    if start not in text:
        return {"type": "text", "function_calls": [], "reference_text": text}
    after = text.split(start, 1)[1]
    if end not in after:
        return {
            "type": "invalid",
            "function_calls": [],
            "reference_text": text,
            "parse_error": "unterminated_tool_call",
        }
    payload = after.split(end, 1)[0].strip()
    try:
        calls = json.loads(payload)
    except json.JSONDecodeError:
        return {
            "type": "invalid",
            "function_calls": [],
            "reference_text": text,
            "parse_error": "invalid_tool_call_json",
        }
    if not isinstance(calls, list):
        return {
            "type": "invalid",
            "function_calls": [],
            "reference_text": text,
            "parse_error": "tool_call_payload_not_list",
        }
    return {
        "type": "call" if calls else "text",
        "function_calls": calls,
        "reference_text": text,
    }


def _result_rows(
    cases: list[dict[str, Any]],
    surface: str,
    responses: list[tuple[dict[str, Any], float]],
) -> list[dict[str, Any]]:
    if surface not in SURFACES:
        raise ValueError("invalid surface")
    if len(responses) != len(cases):
        raise ValueError("surface response count mismatch")
    rows = []
    for case, (response, latency_ms) in zip(cases, responses):
        if not isinstance(response, dict):
            raise ValueError("surface response must be an object")
        latency = float(latency_ms)
        if not math.isfinite(latency) or latency < 0:
            raise ValueError("surface latency must be finite and nonnegative")
        prediction = classify_response(response)
        rows.append(
            {
                "schema_version": RESULT_SCHEMA,
                "surface": surface,
                "case_id": case["case_id"],
                "family_id": case["family_id"],
                "category": case["category"],
                "expected": case["expected"],
                "case_input_sha256": case_input_sha256(case),
                "predicted": prediction,
                "correct": prediction == case["expected"],
                "latency_ms": round(latency, 3),
                "response": response,
            }
        )
    return rows


def validate_surface_rows(
    cases: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    surface: str,
) -> list[dict[str, Any]]:
    expected_ids = [case["case_id"] for case in cases]
    if len(rows) != len(cases):
        raise ValueError("surface result row count mismatch")
    if [row.get("case_id") for row in rows] != expected_ids:
        raise ValueError("surface results must preserve frozen case order")
    by_case = {case["case_id"]: case for case in cases}
    if len(by_case) != len(cases):
        raise ValueError("fixture case IDs not unique")
    for row in rows:
        if row.get("schema_version") != RESULT_SCHEMA or row.get("surface") != surface:
            raise ValueError("surface result schema/surface mismatch")
        case = by_case[row["case_id"]]
        for field in ("family_id", "category", "expected"):
            if row.get(field) != case[field]:
                raise ValueError("surface result fixture projection mismatch")
        if row.get("case_input_sha256") != case_input_sha256(case):
            raise ValueError("surface result input binding mismatch")
        if row.get("predicted") not in ALLOWED_PREDICTIONS:
            raise ValueError("invalid surface prediction")
        if bool(row.get("correct")) != (row["predicted"] == row["expected"]):
            raise ValueError("surface correct flag mismatch")
        latency = row.get("latency_ms")
        if not isinstance(latency, (int, float)) or isinstance(latency, bool):
            raise ValueError("invalid surface latency")
        if not math.isfinite(float(latency)) or float(latency) < 0:
            raise ValueError("invalid surface latency")
        if not isinstance(row.get("response"), dict):
            raise ValueError("surface raw response missing")
        if classify_response(row["response"]) != row["predicted"]:
            raise ValueError("surface prediction/raw response mismatch")
    return rows


def surface_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    positives = [row for row in rows if row["category"] == "positive"]
    negatives = [row for row in rows if row["category"] == "negative"]
    valid_positive_calls = [row for row in positives if row["predicted"] in DECISIONS]
    distribution = collections.Counter(row["predicted"] for row in valid_positive_calls)
    dominant = max(distribution.values()) / len(valid_positive_calls) if valid_positive_calls else 1.0
    latencies = [float(row["latency_ms"]) for row in rows]
    return {
        "rows": len(rows),
        "positive_n": len(positives),
        "positive_correct": sum(bool(row["correct"]) for row in positives),
        "positive_accuracy": sum(bool(row["correct"]) for row in positives) / len(positives),
        "positive_route_calls": len(valid_positive_calls),
        "negative_n": len(negatives),
        "negative_no_call": sum(row["predicted"] == "NO_CALL" for row in negatives),
        "negative_false_call": sum(row["predicted"] in DECISIONS for row in negatives),
        "invalid_predictions": sum(row["predicted"] == "INVALID" for row in rows),
        "dominant_positive_decision_rate": dominant,
        "positive_prediction_distribution": dict(sorted(distribution.items())),
        "latency_ms_mean": sum(latencies) / len(latencies),
        "latency_ms_max": max(latencies),
    }


def pairwise_divergence(
    reference_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if [row["case_id"] for row in reference_rows] != [row["case_id"] for row in candidate_rows]:
        raise ValueError("pairwise comparison case order mismatch")
    mismatches = [
        ref["case_id"]
        for ref, candidate in zip(reference_rows, candidate_rows)
        if ref["predicted"] != candidate["predicted"]
    ]
    ref_metrics = surface_metrics(reference_rows)
    candidate_metrics = surface_metrics(candidate_rows)
    return {
        "prediction_mismatch_count": len(mismatches),
        "prediction_mismatch_case_ids": mismatches,
        "positive_correct_drop": max(
            0, ref_metrics["positive_correct"] - candidate_metrics["positive_correct"]
        ),
        "negative_no_call_drop": max(
            0, ref_metrics["negative_no_call"] - candidate_metrics["negative_no_call"]
        ),
    }


def decide(
    manifest: dict[str, Any],
    base_metrics: dict[str, Any],
    lora_metrics: dict[str, Any],
    built_metrics: dict[str, Any],
    adaptation: dict[str, Any],
    deployment: dict[str, Any],
) -> tuple[str, list[str]]:
    thresholds = manifest["thresholds"]
    reasons = []

    if any(metrics["invalid_predictions"] for metrics in (base_metrics, lora_metrics, built_metrics)):
        return "INCONCLUSIVE", ["invalid_prediction_observed"]

    if deployment["prediction_mismatch_count"] >= thresholds["deployment_pairwise_mismatch_count"]:
        reasons.append("reference_built_pairwise_mismatch")
    if deployment["positive_correct_drop"] >= thresholds["deployment_positive_correct_drop"]:
        reasons.append("built_positive_correctness_drop")
    if deployment["negative_no_call_drop"] >= thresholds["deployment_negative_no_call_drop"]:
        reasons.append("built_negative_no_call_drop")
    if reasons:
        return "DEPLOYMENT_DIVERGENCE_REPRODUCED", reasons

    if adaptation["prediction_mismatch_count"] == 0:
        return "INCONCLUSIVE", ["lora_not_load_bearing_on_canary"]

    applicability = []
    if (
        base_metrics["positive_route_calls"] - lora_metrics["positive_route_calls"]
        >= thresholds["applicability_route_call_drop"]
    ):
        applicability.append("lora_route_call_reachability_drop")
    if (
        base_metrics["negative_no_call"] - lora_metrics["negative_no_call"]
        >= thresholds["applicability_negative_no_call_drop"]
    ):
        applicability.append("lora_negative_no_call_drop")
    if (
        lora_metrics["dominant_positive_decision_rate"]
        > thresholds["dominant_positive_decision_rate_max"]
    ):
        applicability.append("lora_positive_decision_collapse")
    if applicability:
        return "APPLICABILITY_REGRESSION_REPRODUCED", applicability

    return "NO_CURRENT_SIGNAL", ["bounded_canary_thresholds_not_crossed"]


def validate_provenance(
    manifest: dict[str, Any],
    provenance: dict[str, Any],
    surface: str,
) -> None:
    if provenance.get("schema_version") != "theseus.needle3.surface_provenance.v1":
        raise ValueError("unsupported surface provenance schema")
    if provenance.get("surface") != surface:
        raise ValueError("surface provenance mismatch")
    snapshot = manifest["upstream_snapshot"]
    for key in (
        "source_commit",
        "release_tag",
        "release_tag_commit",
        "package_version",
        "wheel_filename",
        "wheel_sha256",
    ):
        if provenance.get(key) != snapshot[key]:
            raise ValueError(f"surface upstream provenance mismatch: {key}")
    if provenance.get("fixture_sha256") != manifest["fixture"]["sha256"]:
        raise ValueError("surface fixture provenance mismatch")
    assets = manifest["published_runtime_assets"]
    expected_checkpoint = assets["base_checkpoint"]
    if provenance.get("base_checkpoint_sha256") != expected_checkpoint["sha256"]:
        raise ValueError("base checkpoint SHA-256 does not match frozen runtime asset")
    if provenance.get("base_checkpoint_size_bytes") != expected_checkpoint["size_bytes"]:
        raise ValueError("base checkpoint size does not match frozen runtime asset")
    if surface == "lora_reference" and not SHA64_RE.fullmatch(
        str(provenance.get("lora_adapter_sha256", ""))
    ):
        raise ValueError("LoRA adapter SHA-256 missing")
    if surface == "built_cact":
        for key in ("lora_adapter_sha256", "built_cact_sha256"):
            if not SHA64_RE.fullmatch(str(provenance.get(key, ""))):
                raise ValueError(f"built surface provenance missing: {key}")
        engine = assets["engine"]
        if provenance.get("engine_version") != engine["version"]:
            raise ValueError("built surface engine version mismatch")
        if provenance.get("engine_platform_tag") != engine["platform_tag"]:
            raise ValueError("built surface engine platform mismatch")
        if provenance.get("engine_binary_sha256") != engine["binary_sha256"]:
            raise ValueError("built surface engine binary mismatch")
        if provenance.get("engine_binary_size_bytes") != engine["binary_size_bytes"]:
            raise ValueError("built surface engine size mismatch")
        base_cact = assets["published_base_cact"]
        if provenance.get("published_base_cact_sha256") != base_cact["sha256"]:
            raise ValueError("published base cact SHA-256 mismatch")
        if provenance.get("published_base_cact_size_bytes") != base_cact["size_bytes"]:
            raise ValueError("published base cact size mismatch")


def make_provenance(
    manifest: dict[str, Any],
    surface: str,
    package_wheel: pathlib.Path,
    base_checkpoint: pathlib.Path,
    *,
    lora_adapter: pathlib.Path | None = None,
    built_cact: pathlib.Path | None = None,
    engine_binary: pathlib.Path | None = None,
    published_base_cact: pathlib.Path | None = None,
) -> dict[str, Any]:
    if surface not in SURFACES:
        raise ValueError("invalid surface")
    snapshot = manifest["upstream_snapshot"]
    if package_wheel.name != snapshot["wheel_filename"]:
        raise ValueError("package wheel filename mismatch")
    wheel_hash = sha256_file(package_wheel)
    if wheel_hash != snapshot["wheel_sha256"]:
        raise ValueError("package wheel SHA-256 mismatch")
    checkpoint_expected = manifest["published_runtime_assets"]["base_checkpoint"]
    checkpoint_identity = verify_file_identity(
        base_checkpoint,
        expected_sha256=checkpoint_expected["sha256"],
        expected_size=checkpoint_expected["size_bytes"],
        label="base checkpoint",
    )

    out = {
        "schema_version": "theseus.needle3.surface_provenance.v1",
        "surface": surface,
        "source_commit": snapshot["source_commit"],
        "release_tag": snapshot["release_tag"],
        "release_tag_commit": snapshot["release_tag_commit"],
        "package_version": snapshot["package_version"],
        "wheel_filename": snapshot["wheel_filename"],
        "wheel_sha256": wheel_hash,
        "fixture_sha256": manifest["fixture"]["sha256"],
        "base_checkpoint_sha256": checkpoint_identity["sha256"],
        "base_checkpoint_size_bytes": checkpoint_identity["size_bytes"],
    }
    if surface in {"lora_reference", "built_cact"}:
        if lora_adapter is None or not lora_adapter.is_file():
            raise ValueError("LoRA adapter missing")
        out["lora_adapter_sha256"] = sha256_file(lora_adapter)
    if surface == "built_cact":
        if built_cact is None or not built_cact.is_file():
            raise ValueError("built .cact missing")
        if engine_binary is None:
            raise ValueError("engine binary missing")
        if published_base_cact is None:
            raise ValueError("published base cact missing")
        engine_expected = manifest["published_runtime_assets"]["engine"]
        engine_identity = verify_file_identity(
            engine_binary,
            expected_sha256=engine_expected["binary_sha256"],
            expected_size=engine_expected["binary_size_bytes"],
            label="runtime engine",
        )
        base_cact_expected = manifest["published_runtime_assets"]["published_base_cact"]
        base_cact_identity = verify_file_identity(
            published_base_cact,
            expected_sha256=base_cact_expected["sha256"],
            expected_size=base_cact_expected["size_bytes"],
            label="published base cact",
        )
        out["built_cact_sha256"] = sha256_file(built_cact)
        out["engine_version"] = engine_expected["version"]
        out["engine_platform_tag"] = engine_expected["platform_tag"]
        out["engine_binary_sha256"] = engine_identity["sha256"]
        out["engine_binary_size_bytes"] = engine_identity["size_bytes"]
        out["published_base_cact_sha256"] = base_cact_identity["sha256"]
        out["published_base_cact_size_bytes"] = base_cact_identity["size_bytes"]
    return out


def build_receipt(
    manifest_path: pathlib.Path,
    results: dict[str, pathlib.Path],
    provenance_paths: dict[str, pathlib.Path],
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    cases = validate_manifest(manifest, manifest_path)
    rows_by_surface = {}
    provenance = {}
    for surface in SURFACES:
        rows = validate_surface_rows(cases, load_jsonl(results[surface]), surface)
        prov = load_json(provenance_paths[surface])
        validate_provenance(manifest, prov, surface)
        rows_by_surface[surface] = rows
        provenance[surface] = {
            **prov,
            "results_path": results[surface].as_posix(),
            "results_sha256": sha256_file(results[surface]),
            "provenance_path": provenance_paths[surface].as_posix(),
            "provenance_sha256": sha256_file(provenance_paths[surface]),
        }

    base_hashes = {
        provenance[surface]["base_checkpoint_sha256"]
        for surface in SURFACES
    }
    if len(base_hashes) != 1:
        raise ValueError("surface chain base checkpoint mismatch")
    if (
        provenance["lora_reference"]["lora_adapter_sha256"]
        != provenance["built_cact"]["lora_adapter_sha256"]
    ):
        raise ValueError("surface chain LoRA adapter mismatch")

    metrics = {surface: surface_metrics(rows_by_surface[surface]) for surface in SURFACES}
    adaptation = pairwise_divergence(
        rows_by_surface["base_reference"],
        rows_by_surface["lora_reference"],
    )
    deployment = pairwise_divergence(
        rows_by_surface["lora_reference"],
        rows_by_surface["built_cact"],
    )
    disposition, reasons = decide(
        manifest,
        metrics["base_reference"],
        metrics["lora_reference"],
        metrics["built_cact"],
        adaptation,
        deployment,
    )
    if disposition not in manifest["allowed_final_dispositions"]:
        raise ValueError("computed disposition is not allowed")

    return {
        "schema_version": RECEIPT_SCHEMA,
        "parent_issue": 65,
        "research_parent_issue": 61,
        "manifest_sha256": sha256_file(manifest_path),
        "fixture_sha256": manifest["fixture"]["sha256"],
        "upstream_snapshot": manifest["upstream_snapshot"],
        "surface_provenance": provenance,
        "metrics": metrics,
        "base_reference_vs_lora_reference": adaptation,
        "lora_reference_vs_built_cact": deployment,
        "disposition": disposition,
        "disposition_reasons": reasons,
        "interpretation_boundary": manifest["interpretation_boundary"],
    }


def _load_integration_faults_module():
    path = ROOT / "scripts" / "integration_faults.py"
    spec = importlib.util.spec_from_file_location("needle_canary_integration_faults", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load promoted integration fault contract")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_missing_artifact_fault(
    surface: str,
    expected_artifact: pathlib.Path,
    checkpoint_path: pathlib.Path,
) -> dict[str, Any]:
    if surface not in SURFACES:
        raise ValueError("invalid canary surface")
    if expected_artifact.exists():
        raise ValueError("artifact exists; ARTIFACT_MISSING is not verified")
    fault_module = _load_integration_faults_module()
    checkpoint = fault_module.load_json(checkpoint_path)
    observation = {
        "fault_class": "ARTIFACT_MISSING",
        "evidence_status": "VERIFIED",
        "classification_source": "EXPLICIT_OBSERVATION",
        "observed_surface": surface,
        "metric_or_check": "artifact_presence",
        "observed_value": False,
        "expected_or_reference_value": True,
        "notes": f"Needle 3 canary expected artifact absent: {expected_artifact}",
    }
    return fault_module.build_receipt(
        observation,
        checkpoint,
        checkpoint_sha256=sha256_file(checkpoint_path),
        taxonomy=fault_module.load_taxonomy(),
    )


def _run_reference(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    cases = validate_manifest(manifest, args.manifest)
    verify_installed_package(manifest)

    from needle.model.architecture import SimpleAttentionNetwork
    from needle.model.checkpoints import read_adapter
    from needle.model.finetune import merge_lora
    from needle.model.run import build_prompt, generate, load_checkpoint
    from needle.model.tokenizer import get_tokenizer

    params, config = load_checkpoint(str(args.checkpoint))
    surface = "base_reference"
    if args.lora:
        adapter = read_adapter(str(args.lora))
        lora = {
            tuple(key.split("/")): {
                "A": value["A"],
                "B": value["B"],
            }
            for key, value in adapter["lora"].items()
        }
        params = merge_lora(params, lora, adapter["scale"])
        surface = "lora_reference"

    model = SimpleAttentionNetwork(config)
    tokenizer = get_tokenizer(config.vocab_size)
    responses = []
    for case in cases:
        prompt = build_prompt(case["query"], case["tools"])
        started = time.perf_counter()
        text = generate(
            model,
            params,
            tokenizer,
            prompt,
            max_new_tokens=args.max_new_tokens,
            temperature=0.0,
            seed=0,
            stream=False,
        )
        latency = (time.perf_counter() - started) * 1000.0
        responses.append((reference_text_to_response(text), latency))
    write_jsonl(args.output, _result_rows(cases, surface, responses))
    return 0


def _run_built(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    cases = validate_manifest(manifest, args.manifest)
    verify_installed_package(manifest)
    import needle

    responses = []
    for case in cases:
        agent = needle.Needle(
            tools=case["tools"],
            weights=str(args.weights),
            auto_date=False,
        )
        started = time.perf_counter()
        response = agent.complete(case["query"], max_new_tokens=args.max_new_tokens)
        latency = (time.perf_counter() - started) * 1000.0
        responses.append((response, latency))
        close = getattr(agent, "close", None)
        if callable(close):
            close()
    write_jsonl(args.output, _result_rows(cases, "built_cact", responses))
    return 0


def resolve_engine_path(needle_module: Any) -> pathlib.Path:
    resolver = getattr(needle_module, "_library_path", None)
    if not callable(resolver):
        raise RuntimeError("installed Needle does not expose _library_path")
    path = pathlib.Path(resolver(3)).expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"resolved Needle 3 engine does not exist: {path}")
    return path


def _verify_base_checkpoint(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    validate_manifest(manifest, args.manifest)
    expected = manifest["published_runtime_assets"]["base_checkpoint"]
    identity = verify_file_identity(
        args.checkpoint,
        expected_sha256=expected["sha256"],
        expected_size=expected["size_bytes"],
        label="base checkpoint",
    )
    if args.output is not None:
        write_json(
            args.output,
            {
                "schema_version": "theseus.needle3.published_asset_identity.v1",
                "asset": "base_checkpoint",
                "repository": manifest["published_runtime_assets"]["repository"],
                "repository_revision": manifest["published_runtime_assets"]["repository_revision"],
                **identity,
            },
        )
    print(
        "NEEDLE3_BASE_CHECKPOINT_VERIFIED=PASS "
        f"SHA256={identity['sha256']} SIZE={identity['size_bytes']}"
    )
    return 0


def _verify_wheel(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    validate_manifest(manifest, args.manifest)
    expected = manifest["upstream_snapshot"]
    if args.wheel.name != expected["wheel_filename"]:
        raise SystemExit("NEEDLE3_WHEEL_FILENAME_MISMATCH")
    digest = sha256_file(args.wheel)
    if digest != expected["wheel_sha256"]:
        raise SystemExit("NEEDLE3_WHEEL_SHA256_MISMATCH")
    print(
        "NEEDLE3_WHEEL_VERIFIED=PASS "
        f"FILENAME={args.wheel.name} SHA256={digest}"
    )
    return 0


def _resolve_engine(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    validate_manifest(manifest, args.manifest)
    verify_installed_package(manifest)
    import needle
    from needle.agent import fetch

    expected = manifest["published_runtime_assets"]["engine"]
    observed_tag = fetch._platform_tag()
    if observed_tag != expected["platform_tag"]:
        raise RuntimeError(
            f"runtime engine platform mismatch: expected {expected['platform_tag']}, observed {observed_tag}"
        )
    if fetch.engine_version(3) != expected["version"]:
        raise RuntimeError("runtime engine version mismatch")
    path = resolve_engine_path(needle)
    identity = verify_file_identity(
        path,
        expected_sha256=expected["binary_sha256"],
        expected_size=expected["binary_size_bytes"],
        label="runtime engine",
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(path.as_posix() + "\n", encoding="utf-8")
    if args.identity_output is not None:
        write_json(
            args.identity_output,
            {
                "schema_version": "theseus.needle3.published_asset_identity.v1",
                "asset": "runtime_engine",
                "repository": manifest["published_runtime_assets"]["repository"],
                "repository_revision": manifest["published_runtime_assets"]["repository_revision"],
                "engine_version": expected["version"],
                "platform_tag": observed_tag,
                **identity,
            },
        )
    print(
        "NEEDLE3_RUNTIME_ENGINE_VERIFIED=PASS "
        f"PLATFORM={observed_tag} SHA256={identity['sha256']} SIZE={identity['size_bytes']}"
    )
    return 0


def resolve_published_base_cact_path() -> pathlib.Path:
    from needle.agent import fetch

    return (
        pathlib.Path(fetch.cache_dir(3))
        / fetch.base_weights(3)
    ).expanduser().resolve()


def _resolve_published_base_cact(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    validate_manifest(manifest, args.manifest)
    verify_installed_package(manifest)
    expected = manifest["published_runtime_assets"]["published_base_cact"]
    path = resolve_published_base_cact_path()
    identity = verify_file_identity(
        path,
        expected_sha256=expected["sha256"],
        expected_size=expected["size_bytes"],
        label="published base cact",
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(path.as_posix() + "\n", encoding="utf-8")
    if args.identity_output is not None:
        write_json(
            args.identity_output,
            {
                "schema_version": "theseus.needle3.published_asset_identity.v1",
                "asset": "published_base_cact",
                "repository": manifest["published_runtime_assets"]["repository"],
                "repository_revision": manifest["published_runtime_assets"]["repository_revision"],
                **identity,
            },
        )
    print(
        "NEEDLE3_BASE_CACT_VERIFIED=PASS "
        f"SHA256={identity['sha256']} SIZE={identity['size_bytes']}"
    )
    return 0

def _make_provenance(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    validate_manifest(manifest, args.manifest)
    value = make_provenance(
        manifest,
        args.surface,
        args.package_wheel,
        args.base_checkpoint,
        lora_adapter=args.lora_adapter,
        built_cact=args.built_cact,
        engine_binary=args.engine_binary,
        published_base_cact=args.published_base_cact,
    )
    write_json(args.output, value)
    print(
        "NEEDLE3_SURFACE_PROVENANCE=PASS "
        f"SURFACE={args.surface} BASE_SHA256={value['base_checkpoint_sha256']}"
    )
    return 0


def _validate_receipt(args: argparse.Namespace) -> int:
    expected = load_json(args.receipt)
    rebuilt = build_receipt(
        args.manifest,
        {
            "base_reference": args.base_results,
            "lora_reference": args.lora_results,
            "built_cact": args.built_results,
        },
        {
            "base_reference": args.base_provenance,
            "lora_reference": args.lora_provenance,
            "built_cact": args.built_provenance,
        },
    )
    if expected != rebuilt:
        raise SystemExit("NEEDLE3_CANARY_RECEIPT_MISMATCH")
    print(
        "NEEDLE3_CANARY_RECEIPT_VALID=PASS "
        f"DISPOSITION={rebuilt['disposition']} "
        f"MISMATCHES={rebuilt['lora_reference_vs_built_cact']['prediction_mismatch_count']}"
    )
    return 0


def _aggregate(args: argparse.Namespace) -> int:
    receipt = build_receipt(
        args.manifest,
        {
            "base_reference": args.base_results,
            "lora_reference": args.lora_results,
            "built_cact": args.built_results,
        },
        {
            "base_reference": args.base_provenance,
            "lora_reference": args.lora_provenance,
            "built_cact": args.built_provenance,
        },
    )
    write_json(args.output, receipt)
    print(
        "NEEDLE3_CANARY_RECEIPT=PASS "
        f"DISPOSITION={receipt['disposition']} "
        f"MISMATCHES={receipt['lora_reference_vs_built_cact']['prediction_mismatch_count']}"
    )
    return 0


def _missing_artifact(args: argparse.Namespace) -> int:
    receipt = build_missing_artifact_fault(args.surface, args.expected_artifact, args.checkpoint)
    write_json(args.output, receipt)
    print(
        "NEEDLE3_CANARY_FAULT=PASS "
        f"CLASS={receipt['fault_class']} STATE={receipt['mapped_state']}"
    )
    return 0


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Needle 3 deployment-equivalence canary harness.")
    parser.add_argument("--manifest", type=pathlib.Path, default=DEFAULT_MANIFEST)
    sub = parser.add_subparsers(dest="command", required=True)

    ref = sub.add_parser("run-reference")
    ref.add_argument("--checkpoint", type=pathlib.Path, required=True)
    ref.add_argument("--lora", type=pathlib.Path)
    ref.add_argument("--max-new-tokens", type=int, default=128)
    ref.add_argument("--output", type=pathlib.Path, required=True)
    ref.set_defaults(func=_run_reference)

    built = sub.add_parser("run-built")
    built.add_argument("--weights", type=pathlib.Path, required=True)
    built.add_argument("--max-new-tokens", type=int, default=128)
    built.add_argument("--output", type=pathlib.Path, required=True)
    built.set_defaults(func=_run_built)

    verify_checkpoint = sub.add_parser("verify-base-checkpoint")
    verify_checkpoint.add_argument("--checkpoint", type=pathlib.Path, required=True)
    verify_checkpoint.add_argument("--output", type=pathlib.Path)
    verify_checkpoint.set_defaults(func=_verify_base_checkpoint)

    verify_wheel = sub.add_parser("verify-wheel")
    verify_wheel.add_argument("--wheel", type=pathlib.Path, required=True)
    verify_wheel.set_defaults(func=_verify_wheel)

    resolve_engine = sub.add_parser("resolve-engine")
    resolve_engine.add_argument("--output", type=pathlib.Path)
    resolve_engine.add_argument("--identity-output", type=pathlib.Path)
    resolve_engine.set_defaults(func=_resolve_engine)

    resolve_base_cact = sub.add_parser("resolve-published-base-cact")
    resolve_base_cact.add_argument("--output", type=pathlib.Path)
    resolve_base_cact.add_argument("--identity-output", type=pathlib.Path)
    resolve_base_cact.set_defaults(func=_resolve_published_base_cact)

    provenance = sub.add_parser("make-provenance")
    provenance.add_argument("--surface", choices=SURFACES, required=True)
    provenance.add_argument("--package-wheel", type=pathlib.Path, required=True)
    provenance.add_argument("--base-checkpoint", type=pathlib.Path, required=True)
    provenance.add_argument("--lora-adapter", type=pathlib.Path)
    provenance.add_argument("--built-cact", type=pathlib.Path)
    provenance.add_argument("--engine-binary", type=pathlib.Path)
    provenance.add_argument("--published-base-cact", type=pathlib.Path)
    provenance.add_argument("--output", type=pathlib.Path, required=True)
    provenance.set_defaults(func=_make_provenance)

    validate = sub.add_parser("validate-receipt")
    validate.add_argument("--receipt", type=pathlib.Path, required=True)
    validate.add_argument("--base-results", type=pathlib.Path, required=True)
    validate.add_argument("--lora-results", type=pathlib.Path, required=True)
    validate.add_argument("--built-results", type=pathlib.Path, required=True)
    validate.add_argument("--base-provenance", type=pathlib.Path, required=True)
    validate.add_argument("--lora-provenance", type=pathlib.Path, required=True)
    validate.add_argument("--built-provenance", type=pathlib.Path, required=True)
    validate.set_defaults(func=_validate_receipt)

    aggregate = sub.add_parser("aggregate")
    aggregate.add_argument("--base-results", type=pathlib.Path, required=True)
    aggregate.add_argument("--lora-results", type=pathlib.Path, required=True)
    aggregate.add_argument("--built-results", type=pathlib.Path, required=True)
    aggregate.add_argument("--base-provenance", type=pathlib.Path, required=True)
    aggregate.add_argument("--lora-provenance", type=pathlib.Path, required=True)
    aggregate.add_argument("--built-provenance", type=pathlib.Path, required=True)
    aggregate.add_argument("--output", type=pathlib.Path, required=True)
    aggregate.set_defaults(func=_aggregate)

    missing = sub.add_parser("missing-artifact-fault")
    missing.add_argument("--surface", choices=SURFACES, required=True)
    missing.add_argument("--expected-artifact", type=pathlib.Path, required=True)
    missing.add_argument("--checkpoint", type=pathlib.Path, required=True)
    missing.add_argument("--output", type=pathlib.Path, required=True)
    missing.set_defaults(func=_missing_artifact)

    return parser


def main() -> int:
    args = parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
