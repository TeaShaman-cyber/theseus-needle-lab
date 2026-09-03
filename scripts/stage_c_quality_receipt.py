from __future__ import annotations

import collections

SEMANTIC_DECISIONS = {"PROBE", "READY", "UNKNOWN"}


def _expected_applicability(row: dict) -> str:
    return "NONE" if row.get("expected") == "NO_CALL" else "ROUTE"


def _predicted_applicability(row: dict) -> str:
    predicted = row.get("predicted")
    if predicted == "NO_CALL":
        return "NONE"
    if predicted in SEMANTIC_DECISIONS:
        return "ROUTE"
    return "INVALID"


def scope_metrics(rows: list[dict]) -> dict:
    positives = [r for r in rows if str(r.get("category", "")).endswith("_positive")]
    negatives = [r for r in rows if str(r.get("category", "")).endswith("_negative")]

    app_conf = collections.Counter()
    semantic_conf = collections.Counter()
    semantic_predictions = collections.Counter()
    runtime_or_invalid = 0
    observed_valid_applicability = set()

    for row in rows:
        expected_app = _expected_applicability(row)
        predicted_app = _predicted_applicability(row)
        app_conf[f"{expected_app}->{predicted_app}"] += 1
        if predicted_app in {"NONE", "ROUTE"}:
            observed_valid_applicability.add(predicted_app)
        else:
            runtime_or_invalid += 1

        if expected_app == "ROUTE" and row.get("predicted") in SEMANTIC_DECISIONS:
            semantic_conf[f"{row.get('expected')}->{row.get('predicted')}"] += 1
            semantic_predictions[row.get("predicted")] += 1

    semantic_total = sum(semantic_predictions.values())
    dominant = max(semantic_predictions.values()) / semantic_total if semantic_total else 1.0
    return {
        "positive_n": len(positives),
        "positive_correct": sum(bool(r.get("correct")) for r in positives),
        "negative_n": len(negatives),
        "negative_no_call": sum(r.get("predicted") == "NO_CALL" for r in negatives),
        "applicability_confusion": dict(sorted(app_conf.items())),
        "semantic_confusion": dict(sorted(semantic_conf.items())),
        "semantic_prediction_distribution": dict(sorted(semantic_predictions.items())),
        "dominant_semantic_decision_rate": dominant,
        "applicability_observed_classes": sorted(observed_valid_applicability),
        "runtime_or_invalid": runtime_or_invalid,
    }


def evaluate_replica_pair(arm_a_heldout: list[dict], arm_b_heldout: list[dict], arm_b_reduced_weight_heldout: list[dict]) -> dict:
    a = scope_metrics(arm_a_heldout)
    b = scope_metrics(arm_b_heldout)
    reduced = scope_metrics(arm_b_reduced_weight_heldout)

    if (a["positive_n"], a["negative_n"]) != (72, 24):
        raise ValueError("unexpected Arm A heldout geometry")
    if (b["positive_n"], b["negative_n"]) != (72, 24):
        raise ValueError("unexpected Arm B heldout geometry")
    if (reduced["positive_n"], reduced["negative_n"]) != (72, 24):
        raise ValueError("unexpected reduced-weight heldout geometry")

    recovery_floor_ok = b["negative_no_call"] >= 20
    positive_floor_ok = b["positive_correct"] >= 32
    dominant_semantic_ok = b["dominant_semantic_decision_rate"] <= 0.70
    applicability_not_collapsed = len(b["applicability_observed_classes"]) >= 2
    reduced_weight_retention_ok = (
        reduced["negative_no_call"] >= 20
        and reduced["positive_correct"] >= 32
        and reduced["dominant_semantic_decision_rate"] <= 0.70
        and len(reduced["applicability_observed_classes"]) >= 2
    )
    paired_specificity_ok = (
        b["negative_no_call"] > a["negative_no_call"]
        and b["positive_correct"] >= a["positive_correct"]
    )

    if not recovery_floor_ok or not reduced_weight_retention_ok:
        disposition = "REJECTED_APPLICABILITY_RECOVERY_FAILED"
    elif not positive_floor_ok:
        disposition = "REJECTED_POSITIVE_RETENTION_REGRESSION"
    elif not dominant_semantic_ok or not applicability_not_collapsed:
        disposition = "REJECTED_DECISION_COLLAPSE"
    elif not paired_specificity_ok:
        disposition = "INCONCLUSIVE_RECOVERY_SPECIFICITY"
    else:
        disposition = "ACCEPTED_REPLICA_STAGE_C_APPLICABILITY_RECOVERY"

    accepted = disposition == "ACCEPTED_REPLICA_STAGE_C_APPLICABILITY_RECOVERY"
    return {
        "arm_a": a,
        "arm_b": b,
        "arm_b_reduced_weight": reduced,
        "recovery_floor_ok": recovery_floor_ok,
        "positive_floor_ok": positive_floor_ok,
        "dominant_semantic_ok": dominant_semantic_ok,
        "applicability_not_collapsed": applicability_not_collapsed,
        "reduced_weight_retention_ok": reduced_weight_retention_ok,
        "paired_specificity_ok": paired_specificity_ok,
        "accepted": accepted,
        "disposition": disposition,
    }


def final_disposition(r1: dict, r2: dict) -> str:
    if r1.get("accepted") and r2.get("accepted"):
        return "ACCEPTED_STAGE_C_APPLICABILITY_RECOVERY"
    priority = [
        "REJECTED_APPLICABILITY_RECOVERY_FAILED",
        "REJECTED_POSITIVE_RETENTION_REGRESSION",
        "REJECTED_DECISION_COLLAPSE",
        "INCONCLUSIVE_RECOVERY_SPECIFICITY",
    ]
    observed = {r1.get("disposition"), r2.get("disposition")}
    for disposition in priority:
        if disposition in observed:
            return disposition
    return "INCONCLUSIVE_REPLICA_DIVERGENCE"
