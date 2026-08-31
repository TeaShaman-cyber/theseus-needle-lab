#!/usr/bin/env python3
import argparse
import json
import pathlib

import numpy as np


def coverage_record(*, prompt_tokens: int, target_tokens: int, cap: int) -> dict:
    total_tokens = 1 + prompt_tokens + target_tokens + 1
    available_for_target = max(0, cap - (1 + prompt_tokens))
    retained = min(target_tokens, available_for_target)
    return {
        "prompt_tokens": prompt_tokens,
        "target_tokens": target_tokens,
        "total_tokens": total_tokens,
        "target_tokens_retained": retained,
        "target_complete": retained == target_tokens,
        "eos_kept": cap >= total_tokens,
    }


def validation_rows(count: int, val_split: float) -> set[int]:
    n_val = min(int(count * val_split), count - 1)
    if n_val <= 0:
        return set()
    order = np.random.default_rng(0).permutation(count)
    return {int(i) + 1 for i in order[:n_val]}


def analyze(data: pathlib.Path, cap: int, val_split: float = 0.1) -> dict:
    from needle.model.finetune import fit_max_len, render_example
    from needle.model.tokenizer import get_tokenizer

    rows = [json.loads(line) for line in data.read_text().splitlines() if line.strip()]
    tokenizer = get_tokenizer()
    effective_max_len = int(fit_max_len(str(data), tokenizer, cap))
    val_rows = validation_rows(len(rows), val_split)
    records = []
    for row_number, raw in enumerate(rows, start=1):
        prompt, target = render_example(raw)
        rec = coverage_record(
            prompt_tokens=len(tokenizer.encode(prompt)),
            target_tokens=len(tokenizer.encode(target)),
            cap=effective_max_len,
        )
        answers = raw.get("answers") or []
        decision = None
        if answers:
            decision = (answers[0].get("arguments") or {}).get("decision")
        rec.update({
            "row": row_number,
            "membership": "validation" if row_number in val_rows else "training",
            "decision": decision,
        })
        records.append(rec)
    training_truncated = [
        r["row"] for r in records
        if r["membership"] == "training" and (not r["target_complete"] or not r["eos_kept"])
    ]
    return {
        "schema": "theseus.needle.target_coverage.v1",
        "data": str(data),
        "cap": cap,
        "effective_max_len": effective_max_len,
        "val_split": val_split,
        "validation_rows": sorted(val_rows),
        "rows": records,
        "summary": {
            "row_count": len(records),
            "training_rows": sum(r["membership"] == "training" for r in records),
            "validation_rows": sum(r["membership"] == "validation" for r in records),
            "training_truncated_rows": training_truncated,
        },
    }


def assert_full_training_targets(report: dict) -> None:
    bad = report["summary"]["training_truncated_rows"]
    if bad:
        raise SystemExit(f"training targets truncated: {bad}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True, type=pathlib.Path)
    p.add_argument("--cap", required=True, type=int)
    p.add_argument("--output", required=True, type=pathlib.Path)
    p.add_argument("--val-split", type=float, default=0.1)
    p.add_argument("--assert-full-training-targets", action="store_true")
    args = p.parse_args()
    report = analyze(args.data, args.cap, args.val_split)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["summary"], sort_keys=True))
    if args.assert_full_training_targets:
        assert_full_training_targets(report)


if __name__ == "__main__":
    main()
