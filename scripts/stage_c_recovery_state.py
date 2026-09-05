from __future__ import annotations

from copy import deepcopy

VALID_OUTCOMES = {"FALSE_CALL", "CORRECT_NO_CALL", "OTHER"}


def _zone(priority: float, last_outcome: str) -> tuple[str, bool]:
    if last_outcome == "FALSE_CALL":
        return "recent", False
    if priority >= 1.0:
        return "active", False
    return "normal", True


def update_recovery_entry(entry: dict, outcome: str, policy: dict) -> dict:
    if outcome not in VALID_OUTCOMES:
        raise ValueError("invalid recovery outcome")
    out = deepcopy(entry)
    if outcome == "FALSE_CALL":
        out["failure_count"] += 1
        out["success_streak"] = 0
        out["recovery_priority"] = min(
            float(policy["max_priority"]),
            float(out["recovery_priority"]) + float(policy["false_call_increment"]),
        )
    elif outcome == "CORRECT_NO_CALL":
        out["success_streak"] += 1
        if out["success_streak"] % int(policy["successes_before_decay"]) == 0:
            out["recovery_priority"] = max(
                float(policy["min_active_priority"]),
                float(out["recovery_priority"]) * float(policy["success_decay_factor"]),
            )
    else:
        out["success_streak"] = 0
    out["last_outcome"] = outcome
    out["retention_zone"], out["evictable"] = _zone(float(out["recovery_priority"]), outcome)
    return out


def build_recovery_state(semantic_rows: list[dict], outcome_rows: list[dict], policy: dict) -> list[dict]:
    semantic_by_id = {row["case_id"]: row for row in semantic_rows}
    if any(row.get("split") != "train" for row in semantic_rows):
        raise ValueError("heldout rows are forbidden in recovery state")
    state_by_id = {}
    for outcome_row in outcome_rows:
        case_id = outcome_row["id"]
        semantic = semantic_by_id.get(case_id)
        if semantic is None:
            raise ValueError(f"unknown recovery case_id: {case_id}")
        if semantic.get("applicability") != "none" or semantic.get("expected_decision") is not None:
            continue
        predicted = outcome_row.get("predicted")
        outcome = "CORRECT_NO_CALL" if predicted == "NO_CALL" else "FALSE_CALL" if predicted in {"PROBE", "READY", "UNKNOWN"} else "OTHER"
        entry = state_by_id.get(case_id)
        if entry is None:
            entry = {
                "case_id": case_id,
                "class": "negative_boundary",
                "failure_count": 0,
                "success_streak": 0,
                "recovery_priority": 0.0,
                "last_outcome": "OTHER",
                "retention_zone": "normal",
                "evictable": True,
            }
        state_by_id[case_id] = update_recovery_entry(entry, outcome, policy)
    return sorted(state_by_id.values(), key=lambda row: row["case_id"])
