#!/usr/bin/env python3
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import pathlib

DECISIONS = {"PROBE", "READY", "UNKNOWN"}
COLLAPSE_THRESHOLD = 0.75


def load_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def score(records: list[dict]) -> dict:
    n = len(records)
    valid = sum(bool(row.get("valid_structured_call")) for row in records)
    correct = sum(bool(row.get("correct")) for row in records)
    semantic = [row.get("predicted") for row in records if row.get("predicted") in DECISIONS]
    semantic_counts = Counter(semantic)
    dominant_prediction = None
    dominant_rate = None
    if semantic_counts:
        dominant_prediction, dominant_n = sorted(semantic_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        dominant_rate = dominant_n / len(semantic)
    raw_counts = Counter(row.get("predicted_label") for row in records)
    first = records[0]
    return {
        "n": n,
        "valid_calls": valid,
        "valid_call_rate": valid / n if n else None,
        "correct": correct,
        "decision_accuracy": correct / n if n else None,
        "prediction_distribution": dict(sorted(Counter(row.get("predicted") for row in records).items())),
        "raw_label_distribution": dict(sorted(raw_counts.items())),
        "semantic_prediction_n": len(semantic),
        "dominant_prediction": dominant_prediction,
        "dominant_prediction_rate": dominant_rate,
        "collapsed": bool(dominant_rate is not None and dominant_rate >= COLLAPSE_THRESHOLD),
        "label_tokenization": first.get("label_tokenization", {}),
        "prediction_vector": [
            {
                "id": row["id"],
                "expected": row["expected"],
                "predicted_label": row["predicted_label"],
                "predicted": row["predicted"],
                "valid_structured_call": bool(row.get("valid_structured_call")),
                "correct": bool(row.get("correct")),
            }
            for row in records
        ],
    }


def build_receipt(arms: dict[str, list[dict]], *, commit: str, run_id: str) -> dict:
    if set(arms) != set("ABC"):
        raise ValueError("expected arms A/B/C")
    for name, rows in arms.items():
        if not rows:
            raise ValueError(f"arm {name} is empty")
    return {
        "schema": "theseus.needle.semantic_verbalizer_preflight.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "repository": "TeaShaman-cyber/theseus-needle-lab",
            "commit": commit,
            "run_id": str(run_id),
            "cactus_needle_version": "2.0.8",
            "parent_issue": 26,
            "predecessor_commit": "2c674600c17c06ced1683fe72af9c2ab22fa0927",
        },
        "arms": {name: score(rows) for name, rows in arms.items()},
        "prompt_contracts": {
            name: (
                {
                    "schema_json": rows[0]["schema_json"],
                    "framed_query_prefix": rows[0]["framed_query"].removesuffix(rows[0]["source_query"]),
                }
                if all(key in rows[0] for key in ("schema_json", "framed_query", "source_query"))
                else {}
            )
            for name, rows in arms.items()
        },
        "collapse_threshold": COLLAPSE_THRESHOLD,
        "interpretation_boundary": "zero_training_interface_prior_selection_not_evidence_of_learned_policy",
    }


def markdown(receipt: dict) -> str:
    lines = [
        "# Needle semantic verbalizer preflight",
        "",
        "| Arm | Representation | Valid calls | Accuracy | Dominant semantic prediction | Collapse |",
        "|---|---|---:|---:|---|---|",
    ]
    reps = {"A": "PROBE/READY/UNKNOWN", "B": "probe/ready/unknown", "C": "check/ready/unknown"}
    for name in "ABC":
        row = receipt["arms"][name]
        dom = "-" if row["dominant_prediction"] is None else f"{row['dominant_prediction']} {row['dominant_prediction_rate']:.3f}"
        lines.append(
            f"| {name} | {reps[name]} | {row['valid_calls']}/{row['n']} | "
            f"{row['decision_accuracy']:.3f} | {dom} | {row['collapsed']} |"
        )
    lines.extend([
        "",
        "Zero-training interface-prior preflight only; this is not evidence of learned policy.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    for name in "abc":
        p.add_argument(f"--arm-{name}", required=True)
    p.add_argument("--commit", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--markdown")
    args = p.parse_args()
    arms = {name.upper(): load_jsonl(pathlib.Path(getattr(args, f"arm_{name}"))) for name in "abc"}
    receipt = build_receipt(arms, commit=args.commit, run_id=args.run_id)
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    if args.markdown:
        pathlib.Path(args.markdown).write_text(markdown(receipt))


if __name__ == "__main__":
    main()
