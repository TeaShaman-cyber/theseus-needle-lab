from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import datetime

SCHEMA_VERSION = "needle-watch-receipt-v0.2"

TOP_LEVEL_FIELDS = (
    "schema_version",
    "run_id",
    "generated_at",
    "window_start",
    "window_end",
    "collector_revision",
    "source_health",
    "candidates",
)

CANDIDATE_FIELDS = (
    "source_id",
    "source_class",
    "source_entity_id",
    "canonical_url",
    "title",
    "observed_at",
    "published_or_pushed_at",
    "source_identity",
    "upstream_revision",
    "discovery_route",
    "matched_watch_lines",
    "content_fingerprint",
)

HEALTH_FIELDS = (
    "source_id",
    "status",
    "checked_at",
    "records_seen",
    "total_count",
    "returned_count",
    "incomplete_results",
    "truncated",
    "cursor_or_watermark",
    "error_class",
)


def stable_candidate_id(
    source_class: str,
    canonical_url: str,
    source_identity: str,
    content_fingerprint: str,
) -> str:
    payload = "\0".join(
        (source_class, canonical_url, source_identity, content_fingerprint)
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize_candidate(
    raw: dict,
    prior_ids: set[str],
    prior_entity_ids: set[str],
) -> dict:
    candidate = {field: deepcopy(raw.get(field)) for field in CANDIDATE_FIELDS}
    candidate_id = stable_candidate_id(
        candidate["source_class"],
        candidate["canonical_url"],
        candidate["source_identity"],
        candidate["content_fingerprint"],
    )
    candidate["candidate_id"] = candidate_id
    candidate["seen_in_previous_snapshot"] = candidate_id in prior_ids
    candidate["entity_seen_in_previous_snapshot"] = (
        candidate["source_entity_id"] in prior_entity_ids
    )
    return candidate


def build_receipt(
    *,
    run_id: str,
    generated_at: str,
    window_start: str,
    window_end: str,
    collector_revision: str,
    source_health: list[dict],
    candidates: list[dict],
    prior_ids: set[str],
    prior_entity_ids: set[str] | None = None,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "window_start": window_start,
        "window_end": window_end,
        "collector_revision": collector_revision,
        "source_health": deepcopy(source_health),
        "candidates": [
            normalize_candidate(item, prior_ids, prior_entity_ids or set())
            for item in candidates
        ],
    }


def validate_receipt(receipt: dict) -> list[str]:
    errors: list[str] = []
    for field in TOP_LEVEL_FIELDS:
        if field not in receipt:
            errors.append(f"missing top-level field: {field}")

    if receipt.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")

    try:
        window_start = datetime.fromisoformat(
            receipt["window_start"].replace("Z", "+00:00")
        )
        window_end = datetime.fromisoformat(
            receipt["window_end"].replace("Z", "+00:00")
        )
    except (KeyError, AttributeError, TypeError, ValueError):
        errors.append("window_start and window_end must be valid RFC3339 timestamps")
    else:
        if window_start >= window_end:
            errors.append("window_start must be before window_end")

    source_health = receipt.get("source_health")
    if not isinstance(source_health, list) or not source_health:
        errors.append("source_health must contain at least one record")
    else:
        for index, health in enumerate(source_health):
            missing = [field for field in HEALTH_FIELDS if field not in health]
            if missing:
                errors.append(
                    f"source_health[{index}] missing fields: {', '.join(missing)}"
                )
            if health.get("status") not in {"ok", "partial", "failed"}:
                errors.append(f"source_health[{index}] has invalid status")
            if health.get("status") == "ok" and (
                health.get("incomplete_results") is not False
                or health.get("truncated") is not False
            ):
                errors.append(
                    f"source_health[{index}] status ok requires complete coverage"
                )

    candidates = receipt.get("candidates")
    if not isinstance(candidates, list):
        errors.append("candidates must be a list")
    else:
        for index, candidate in enumerate(candidates):
            required = CANDIDATE_FIELDS + (
                "candidate_id",
                "seen_in_previous_snapshot",
                "entity_seen_in_previous_snapshot",
            )
            missing = [field for field in required if field not in candidate]
            if missing:
                errors.append(
                    f"candidates[{index}] missing fields: {', '.join(missing)}"
                )
                continue
            try:
                expected_id = stable_candidate_id(
                    candidate["source_class"],
                    candidate["canonical_url"],
                    candidate["source_identity"],
                    candidate["content_fingerprint"],
                )
            except (TypeError, AttributeError):
                errors.append(f"candidates[{index}] identity fields must be strings")
            else:
                if candidate["candidate_id"] != expected_id:
                    errors.append(f"candidates[{index}] candidate_id mismatch")

    return errors


def is_valid_null(receipt: dict) -> bool:
    if validate_receipt(receipt):
        return False
    if receipt["candidates"]:
        return False
    return all(item["status"] == "ok" for item in receipt["source_health"])
