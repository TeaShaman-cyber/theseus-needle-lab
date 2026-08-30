#!/usr/bin/env python3
import argparse
import collections
import hashlib
import json
import os
import pathlib
from datetime import datetime, timezone

LABELS = ["PROBE", "READY", "UNKNOWN", "NO_CALL", "INVALID"]
ROUTING = {"PROBE", "READY", "UNKNOWN"}


def _delta(base, tuned):
    if base is None or tuned is None:
        return None
    return tuned - base


def _fmt(value, signed=False):
    if value is None:
        return "n/a"
    return f"{value:+.3f}" if signed else f"{value:.3f}"


def load_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def shared_max_new_tokens(base: list[dict], tuned: list[dict]) -> int | None:
    values = {row.get("max_new_tokens") for row in (base + tuned) if row.get("max_new_tokens") is not None}
    if not values:
        return None
    if len(values) != 1:
        raise ValueError(f"mixed max_new_tokens values: {sorted(values)}")
    return next(iter(values))


def _accuracy(records: list[dict]) -> float | None:
    if not records:
        return None
    return sum(bool(row["correct"]) for row in records) / len(records)


def score(records: list[dict]) -> dict:
    confusion = {expected: {predicted: 0 for predicted in LABELS} for expected in ["PROBE", "READY", "UNKNOWN", "NO_CALL"]}
    for row in records:
        predicted = row["predicted"] if row["predicted"] in LABELS else "INVALID"
        confusion[row["expected"]][predicted] += 1
    routing = [row for row in records if row["expected"] in ROUTING]
    negatives = [row for row in records if row["expected"] == "NO_CALL"]
    categories = sorted({row.get("category", "uncategorized") for row in records})
    return {
        "n": len(records),
        "overall_accuracy": _accuracy(records),
        "routing_accuracy": _accuracy(routing),
        "negative_control_no_call_rate": (
            sum(row["predicted"] == "NO_CALL" for row in negatives) / len(negatives) if negatives else None
        ),
        "invalid_rate": sum(row["predicted"] == "INVALID" for row in records) / len(records) if records else None,
        "mean_latency_ms": (sum(float(row["latency_ms"]) for row in records if "latency_ms" in row) / sum(1 for row in records if "latency_ms" in row)) if any("latency_ms" in row for row in records) else None,
        "category_accuracy": {category: _accuracy([row for row in records if row.get("category", "uncategorized") == category]) for category in categories},
        "confusion": confusion,
    }


def compare(base: list[dict], tuned: list[dict]) -> dict:
    base_by_id = {row["id"]: row for row in base}
    tuned_by_id = {row["id"]: row for row in tuned}
    if set(base_by_id) != set(tuned_by_id):
        raise ValueError("base/tuned case identities differ")
    for case_id in base_by_id:
        if base_by_id[case_id]["expected"] != tuned_by_id[case_id]["expected"]:
            raise ValueError(f"expected label differs for {case_id}")
    base_score = score(base)
    tuned_score = score(tuned)
    changed = []
    for case_id in sorted(base_by_id):
        b, t = base_by_id[case_id], tuned_by_id[case_id]
        if b["predicted"] != t["predicted"]:
            changed.append({
                "id": case_id,
                "expected": b["expected"],
                "base": b["predicted"],
                "tuned": t["predicted"],
                "base_correct": b["correct"],
                "tuned_correct": t["correct"],
            })
    return {
        "base": base_score,
        "tuned": tuned_score,
        "delta": {
            "overall_accuracy": _delta(base_score["overall_accuracy"], tuned_score["overall_accuracy"]),
            "routing_accuracy": _delta(base_score["routing_accuracy"], tuned_score["routing_accuracy"]),
            "negative_control_no_call_rate": _delta(base_score["negative_control_no_call_rate"], tuned_score["negative_control_no_call_rate"]),
        },
        "changed_predictions": changed,
    }


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def markdown(receipt: dict) -> str:
    b, t, d = receipt["comparison"]["base"], receipt["comparison"]["tuned"], receipt["comparison"]["delta"]
    return f"""# Needle policy evaluation result

- Base overall accuracy: {_fmt(b['overall_accuracy'])}
- Tuned overall accuracy: {_fmt(t['overall_accuracy'])}
- Delta overall: {_fmt(d['overall_accuracy'], signed=True)}
- Base routing accuracy: {_fmt(b['routing_accuracy'])}
- Tuned routing accuracy: {_fmt(t['routing_accuracy'])}
- Delta routing: {_fmt(d['routing_accuracy'], signed=True)}
- Base negative-control no-call rate: {_fmt(b['negative_control_no_call_rate'])}
- Tuned negative-control no-call rate: {_fmt(t['negative_control_no_call_rate'])}
- Delta negative-control no-call: {_fmt(d['negative_control_no_call_rate'], signed=True)}
- Changed predictions: {len(receipt['comparison']['changed_predictions'])}

A workflow success means evaluation execution completed. These metrics do not by themselves establish generalization or acceptance authority.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--tuned", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--tuned-artifact", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown", required=True)
    parser.add_argument("--scope", default="bounded_held_out_behavioral_comparison_not_generalization")
    args = parser.parse_args()

    base_path = pathlib.Path(args.base)
    tuned_path = pathlib.Path(args.tuned)
    cases_path = pathlib.Path(args.cases)
    artifact_path = pathlib.Path(args.tuned_artifact)
    base_rows = load_jsonl(base_path)
    tuned_rows = load_jsonl(tuned_path)
    comparison = compare(base_rows, tuned_rows)
    max_new_tokens = shared_max_new_tokens(base_rows, tuned_rows)
    receipt = {
        "schema": "theseus.needle.policy_eval.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": args.scope,
        "source": {
            "repository": os.environ.get("GITHUB_REPOSITORY"),
            "commit": os.environ.get("GITHUB_SHA"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "source_smoke_run_id": "33319821037",
            "source_smoke_commit": "9a9b4bf1083a4fe2f8f732f779ede008ab1c3b75",
        },
        "inputs": {
            "cases_sha256": sha256(cases_path),
            "tuned_cact_sha256": sha256(artifact_path),
            "tuned_cact_size_bytes": artifact_path.stat().st_size,
            "expected_tuned_cact_sha256": "3c0c684888c0d796e1b3a62326fbb1f3cc991f6ee5a0e596ac448df99edef10a",
            "max_new_tokens": max_new_tokens,
        },
        "comparison": comparison,
    }
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    pathlib.Path(args.markdown).write_text(markdown(receipt))


if __name__ == "__main__":
    main()
