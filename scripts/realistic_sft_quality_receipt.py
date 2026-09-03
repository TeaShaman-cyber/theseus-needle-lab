#!/usr/bin/env python3
from __future__ import annotations

import collections

DECISIONS = {"PROBE", "READY", "UNKNOWN"}


def _scope_metrics(rows: list[dict]) -> dict:
    positives = [r for r in rows if str(r.get("category", "")).endswith("_positive")]
    negatives = [r for r in rows if str(r.get("category", "")).endswith("_negative")]
    valid_calls = [r for r in positives if r.get("predicted") in DECISIONS]
    counts = collections.Counter(r.get("predicted") for r in valid_calls)
    dominant = (max(counts.values()) / len(valid_calls)) if valid_calls else 1.0
    return {
        "positive_n": len(positives),
        "positive_correct": sum(bool(r.get("correct")) for r in positives),
        "positive_accuracy": (sum(bool(r.get("correct")) for r in positives) / len(positives)) if positives else None,
        "positive_route_calls": len(valid_calls),
        "negative_n": len(negatives),
        "negative_no_call": sum(r.get("predicted") == "NO_CALL" for r in negatives),
        "dominant_semantic_decision_rate": dominant,
        "prediction_distribution": dict(sorted(counts.items())),
    }


def evaluate_replica(base_train: list[dict], tuned_train: list[dict], base_heldout: list[dict], tuned_heldout: list[dict]) -> dict:
    bt = _scope_metrics(base_train)
    tt = _scope_metrics(tuned_train)
    bh = _scope_metrics(base_heldout)
    th = _scope_metrics(tuned_heldout)
    if tt["positive_n"] != 300 or th["positive_n"] != 72 or th["negative_n"] != 24:
        raise ValueError("unexpected Stage B evaluation geometry")

    train_fit = tt["positive_correct"] >= 210
    heldout_positive_gain_ok = th["positive_correct"] >= bh["positive_correct"] + 6
    heldout_reachability_ok = th["positive_route_calls"] >= bh["positive_route_calls"] - 3
    heldout_negative_no_call_ok = th["negative_no_call"] >= bh["negative_no_call"] - 2
    dominant_decision_ok = th["dominant_semantic_decision_rate"] <= 0.70
    applicability_regression = not heldout_reachability_ok or not heldout_negative_no_call_ok
    learned_and_generalizes = all([
        train_fit,
        heldout_positive_gain_ok,
        heldout_reachability_ok,
        heldout_negative_no_call_ok,
        dominant_decision_ok,
    ])
    return {
        "train": {"base": bt, "tuned": tt},
        "heldout": {"base": bh, "tuned": th},
        "train_fit": train_fit,
        "heldout_positive_gain_ok": heldout_positive_gain_ok,
        "heldout_reachability_ok": heldout_reachability_ok,
        "heldout_negative_no_call_ok": heldout_negative_no_call_ok,
        "dominant_decision_ok": dominant_decision_ok,
        "applicability_regression": applicability_regression,
        "learned_and_generalizes": learned_and_generalizes,
    }


def final_disposition(r1: dict, r2: dict) -> str:
    if r1.get("applicability_regression") or r2.get("applicability_regression"):
        return "REJECTED_APPLICABILITY_REGRESSION"
    successes = sum(bool(r.get("learned_and_generalizes")) for r in (r1, r2))
    if successes == 2:
        return "ACCEPTED_LEARNED_AND_GENERALIZES"
    if successes == 1:
        return "INCONCLUSIVE_REPLICA_DIVERGENCE"
    if not r1.get("train_fit") and not r2.get("train_fit"):
        return "REJECTED_PERSISTENT_UNDERFIT"
    if r1.get("train_fit") and r2.get("train_fit"):
        return "INCONCLUSIVE_TRAIN_FIT_GENERALIZATION_GAP"
    return "INCONCLUSIVE_REPLICA_DIVERGENCE"
