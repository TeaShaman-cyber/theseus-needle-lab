#!/usr/bin/env python3
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import pathlib


def load_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def score(records: list[dict]) -> dict:
    n = len(records)
    valid = sum(bool(row.get("valid_structured_call")) for row in records)
    correct = sum(bool(row.get("correct")) for row in records)
    out = {
        "n": n,
        "valid_calls": valid,
        "valid_call_rate": valid / n if n else None,
        "correct": correct,
        "decision_accuracy": correct / n if n else None,
        "prediction_distribution": dict(sorted(Counter(row.get("predicted") for row in records).items())),
        "prediction_vector": [
            {
                "id": row["id"],
                "expected": row["expected"],
                "predicted": row["predicted"],
                "valid_structured_call": bool(row.get("valid_structured_call")),
                "correct": bool(row.get("correct")),
            }
            for row in records
        ],
    }
    if records and records[0].get("arm") == "D" or any("stage1_expected" in row for row in records):
        stage1_correct = sum(row.get("stage1_predicted") == row.get("stage1_expected") for row in records)
        stage2_expected = [row for row in records if row.get("stage2_expected") is not None]
        stage2_attempted = [row for row in stage2_expected if row.get("stage2_predicted") is not None]
        stage2_correct = sum(row.get("stage2_predicted") == row.get("stage2_expected") for row in stage2_expected)
        out.update({
            "stage1_correct": stage1_correct,
            "stage1_accuracy": stage1_correct / n if n else None,
            "stage2_expected_n": len(stage2_expected),
            "stage2_attempted_n": len(stage2_attempted),
            "stage2_correct": stage2_correct,
            "stage2_accuracy_on_expected": stage2_correct / len(stage2_expected) if stage2_expected else None,
        })
    return out


def _prompt_contract(records: list[dict]) -> dict:
    first = records[0]
    if not any(key in first for key in ("schema_json", "stage1_schema_json")):
        return {}
    if first.get("arm") == "D" or "stage1_schema_json" in first:
        return {
            "stage1_schema_json": first["stage1_schema_json"],
            "stage1_framed_query_prefix": first["stage1_framed_query"].removesuffix(first["source_query"]),
            "stage2_schema_json": first["stage2_schema_json"],
            "stage2_framed_query_prefix": first["stage2_framed_query"].removesuffix(first["source_query"]),
        }
    return {
        "schema_json": first["schema_json"],
        "framed_query_prefix": first["framed_query"].removesuffix(first["source_query"]),
    }


def build_receipt(arms: dict[str, list[dict]], *, commit: str, run_id: str) -> dict:
    if set(arms) != set("ABCD"):
        raise ValueError("expected arms A/B/C/D")
    for name, rows in arms.items():
        if not rows:
            raise ValueError(f"arm {name} is empty")
    return {
        "schema": "theseus.needle.verbalizer_factorized_probe.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "repository": "TeaShaman-cyber/theseus-needle-lab",
            "commit": commit,
            "run_id": str(run_id),
            "cactus_needle_version": "2.0.8",
            "parent_issue": 16,
        },
        "arms": {name: score(rows) for name, rows in arms.items()},
        "prompt_contracts": {name: _prompt_contract(rows) for name, rows in arms.items()},
        "interpretation_boundary": "descriptive_zero_training_representation_probe_not_statistical_significance",
    }


def markdown(receipt: dict) -> str:
    lines = [
        "# Needle verbalizer and factorized-policy probe",
        "",
        "| Arm | Representation | Valid call rate | Decision accuracy | Distribution |",
        "|---|---|---:|---:|---|",
    ]
    reps = {"A": "uppercase", "B": "lowercase", "C": "A/B/C", "D": "factorized"}
    for name in "ABCD":
        row = receipt["arms"][name]
        dist = ", ".join(f"{k}:{v}" for k, v in row["prediction_distribution"].items())
        lines.append(f"| {name} | {reps[name]} | {row['valid_call_rate']:.3f} | {row['decision_accuracy']:.3f} | {dist} |")
    d = receipt["arms"]["D"]
    lines.extend([
        "",
        f"Factorized stage-1 accuracy: {d.get('stage1_accuracy'):.3f}",
        f"Factorized stage-2 attempted/expected: {d.get('stage2_attempted_n')}/{d.get('stage2_expected_n')}",
        f"Factorized stage-2 accuracy on expected: {d.get('stage2_accuracy_on_expected'):.3f}",
        "",
        "Descriptive zero-training probe only; no statistical-significance claim.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    for name in "abcd":
        p.add_argument(f"--arm-{name}", required=True)
    p.add_argument("--commit", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--markdown")
    args = p.parse_args()
    arms = {name.upper(): load_jsonl(pathlib.Path(getattr(args, f"arm_{name}"))) for name in "abcd"}
    receipt = build_receipt(arms, commit=args.commit, run_id=args.run_id)
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    if args.markdown:
        pathlib.Path(args.markdown).write_text(markdown(receipt))


if __name__ == "__main__":
    main()
