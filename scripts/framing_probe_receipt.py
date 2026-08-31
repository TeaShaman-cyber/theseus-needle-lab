#!/usr/bin/env python3
import argparse
import json
import pathlib
from datetime import datetime, timezone


def load_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def score(records: list[dict]) -> dict:
    n = len(records)
    valid = sum(bool(row.get("valid_route_call")) for row in records)
    correct = sum(bool(row.get("correct")) for row in records)
    return {
        "n": n,
        "valid_calls": valid,
        "valid_call_rate": valid / n if n else None,
        "correct": correct,
        "decision_accuracy": correct / n if n else None,
        "prediction_vector": [
            {
                "id": row["id"],
                "expected": row["expected"],
                "predicted": row["predicted"],
                "valid_route_call": bool(row.get("valid_route_call")),
                "correct": bool(row.get("correct")),
            }
            for row in records
        ],
    }


def delta(x, y):
    return None if x is None or y is None else y - x


def build_receipt(canaries: list[dict], arms: dict[str, list[dict]], *, commit: str, run_id: str) -> dict:
    if set(arms) != {"A", "B", "C", "D"}:
        raise ValueError("expected arms A/B/C/D")
    scored = {name: score(rows) for name, rows in arms.items()}
    canary_score = score(canaries)
    canary_pass = (
        len(canaries) == 3
        and canary_score["valid_calls"] == 3
        and canary_score["correct"] == 3
    )

    def effects(metric: str) -> dict:
        a, b, c, d = (scored[x][metric] for x in "ABCD")
        return {
            "prefix_with_bare_schema": delta(a, b),
            "description_without_prefix": delta(a, c),
            "prefix_with_described_schema": delta(c, d),
            "description_with_prefix": delta(b, d),
            "interaction_difference_of_differences": None if None in (a, b, c, d) else (d - c) - (b - a),
        }

    return {
        "schema": "theseus.needle.framing_probe.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "repository": "TeaShaman-cyber/theseus-needle-lab",
            "commit": commit,
            "run_id": str(run_id),
            "cactus_needle_version": "2.0.8",
            "parent_issue": 12,
        },
        "canaries": {**canary_score, "all_pass": canary_pass},
        "arms": scored,
        "effects": {
            "call_rate": effects("valid_call_rate"),
            "decision_accuracy": effects("decision_accuracy"),
        },
        "interpretation_boundary": "descriptive_zero_training_probe_not_statistical_significance",
    }


def markdown(receipt: dict) -> str:
    lines = [
        "# Needle framing probe",
        "",
        f"Canaries all pass: {receipt['canaries']['all_pass']}",
        "",
        "| Arm | Valid call rate | Decision accuracy |",
        "|---|---:|---:|",
    ]
    for name in "ABCD":
        s = receipt["arms"][name]
        lines.append(f"| {name} | {s['valid_call_rate']:.3f} | {s['decision_accuracy']:.3f} |")
    lines.extend(["", "Effects are descriptive only; no statistical-significance claim."])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canaries", required=True)
    for name in "abcd":
        parser.add_argument(f"--arm-{name}", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown")
    args = parser.parse_args()

    receipt = build_receipt(
        load_jsonl(pathlib.Path(args.canaries)),
        {name.upper(): load_jsonl(pathlib.Path(getattr(args, f"arm_{name}"))) for name in "abcd"},
        commit=args.commit,
        run_id=args.run_id,
    )
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    if args.markdown:
        pathlib.Path(args.markdown).write_text(markdown(receipt))


if __name__ == "__main__":
    main()
