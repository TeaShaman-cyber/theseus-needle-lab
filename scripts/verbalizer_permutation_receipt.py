#!/usr/bin/env python3
import argparse
import json
import pathlib
from collections import Counter
from datetime import datetime, timezone

NAMES = ["P1", "P2", "P3", "P4", "P5", "P6"]


def load_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def score(rows: list[dict]) -> dict:
    n = len(rows)
    calls = sum(bool(x.get("valid_structured_call")) for x in rows)
    correct = sum(bool(x.get("correct")) for x in rows)
    return {
        "n": n,
        "valid_calls": calls,
        "valid_call_rate": calls / n if n else None,
        "correct": correct,
        "decision_accuracy": correct / n if n else None,
        "raw_token_distribution": dict(sorted(Counter(x.get("predicted_token") for x in rows).items())),
        "mapped_decision_distribution": dict(sorted(Counter(x.get("predicted") for x in rows).items())),
        "mapping": rows[0].get("mapping") if rows else None,
        "prediction_vector": [
            {
                "id": x["id"],
                "expected": x["expected"],
                "predicted_token": x.get("predicted_token"),
                "predicted": x.get("predicted"),
                "valid_structured_call": bool(x.get("valid_structured_call")),
                "correct": bool(x.get("correct")),
            }
            for x in rows
        ],
    }


def _aligned_ids(arms: dict[str, list[dict]]) -> list[str]:
    ids = [x["id"] for x in arms[NAMES[0]]]
    for name in NAMES[1:]:
        if [x["id"] for x in arms[name]] != ids:
            raise ValueError(f"example order mismatch in {name}")
    return ids


def _stability(arms: dict[str, list[dict]]) -> dict:
    ids = _aligned_ids(arms)
    by_name = {name: {x["id"]: x for x in arms[name]} for name in NAMES}
    details = []
    token_same = 0
    mapped_same = 0
    for example_id in ids:
        tokens = [by_name[name][example_id].get("predicted_token") for name in NAMES]
        mapped = [by_name[name][example_id].get("predicted") for name in NAMES]
        all_token_same = len(set(tokens)) == 1
        all_mapped_same = len(set(mapped)) == 1
        token_same += int(all_token_same)
        mapped_same += int(all_mapped_same)
        details.append({
            "id": example_id,
            "raw_tokens": dict(zip(NAMES, tokens)),
            "mapped_decisions": dict(zip(NAMES, mapped)),
            "all_mapping_same_raw_token": all_token_same,
            "all_mapping_same_project_decision": all_mapped_same,
        })
    n = len(ids)
    return {
        "n": n,
        "all_mapping_same_n": token_same,
        "all_mapping_same_rate": token_same / n if n else None,
        "all_mapping_same_project_decision_n": mapped_same,
        "all_mapping_same_project_decision_rate": mapped_same / n if n else None,
        "examples": details,
    }


def pairwise_raw_agreement(arms: dict[str, list[dict]]) -> dict:
    _aligned_ids(arms)
    result = {}
    for i, left in enumerate(NAMES):
        for right in NAMES[i + 1:]:
            pairs = zip(arms[left], arms[right])
            same = sum(a.get("predicted_token") == b.get("predicted_token") for a, b in pairs)
            n = len(arms[left])
            result[f"{left}-{right}"] = {"same_n": same, "n": n, "rate": same / n if n else None}
    return result


def build_receipt(arms: dict[str, list[dict]], *, commit: str, run_id: str) -> dict:
    if list(arms) != NAMES:
        raise ValueError(f"expected ordered mappings {NAMES}")
    _aligned_ids(arms)
    return {
        "schema": "theseus.needle.verbalizer_permutation_probe.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "repository": "TeaShaman-cyber/theseus-needle-lab",
            "commit": commit,
            "run_id": str(run_id),
            "cactus_needle_version": "2.0.8",
            "parent_issue": 18,
        },
        "arms": {name: score(arms[name]) for name in NAMES},
        "raw_token_stability": _stability(arms),
        "pairwise_raw_token_agreement": pairwise_raw_agreement(arms),
        "interpretation_boundary": "descriptive_zero_training_permutation_probe_not_statistical_significance",
    }


def markdown(receipt: dict) -> str:
    lines = [
        "# Needle A/B/C permutation verbalizer-prior probe",
        "",
        "| Mapping | Accuracy | Call rate | Raw token distribution |",
        "|---|---:|---:|---|",
    ]
    for name in NAMES:
        row = receipt["arms"][name]
        dist = ", ".join(f"{k}:{v}" for k, v in row["raw_token_distribution"].items())
        lines.append(f"| {name} | {row['decision_accuracy']:.3f} | {row['valid_call_rate']:.3f} | {dist} |")
    s = receipt["raw_token_stability"]
    lines.extend([
        "",
        f"All-six raw-token stability: {s['all_mapping_same_n']}/{s['n']} ({s['all_mapping_same_rate']:.3f})",
        f"All-six mapped-decision stability: {s['all_mapping_same_project_decision_n']}/{s['n']} ({s['all_mapping_same_project_decision_rate']:.3f})",
        "",
        "Descriptive zero-training probe only; no statistical-significance claim.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in NAMES:
        parser.add_argument(f"--{name.lower()}", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown")
    args = parser.parse_args()
    arms = {name: load_jsonl(pathlib.Path(getattr(args, name.lower()))) for name in NAMES}
    receipt = build_receipt(arms, commit=args.commit, run_id=args.run_id)
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    if args.markdown:
        pathlib.Path(args.markdown).write_text(markdown(receipt))


if __name__ == "__main__":
    main()
