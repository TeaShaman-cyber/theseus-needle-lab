#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from compare_policy_eval import compare, shared_max_new_tokens


def load_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_receipt(*, train_a, train_b, heldout_a, heldout_b, coverage_a, coverage_b,
                  adapter_a_sha256, adapter_b_sha256, cact_a_sha256, cact_b_sha256, seed) -> dict:
    return {
        "schema": "theseus.needle.maxlen_ab.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "repository": os.environ.get("GITHUB_REPOSITORY"),
            "commit": os.environ.get("GITHUB_SHA"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "parent_issue": 8,
            "upstream_reference": "cactus-compute/needle@ee221ce7c13579d9809209b979a9b7a50936614c",
            "cactus_needle_version": "2.0.8",
        },
        "config": {
            "seed": seed,
            "epochs": 1,
            "batch_size": 2,
            "lr": 1e-4,
            "lora_rank": 4,
            "lora_alpha": 32.0,
            "export_bits": 4,
            "max_new_tokens": shared_max_new_tokens(train_a + heldout_a, train_b + heldout_b),
        },
        "arms": {
            "a": {
                "max_len_cap": coverage_a.get("cap", coverage_a["effective_max_len"]),
                "effective_max_len": coverage_a["effective_max_len"],
                "training_truncated_rows": coverage_a["summary"]["training_truncated_rows"],
                "adapter_sha256": adapter_a_sha256,
                "cact_sha256": cact_a_sha256,
            },
            "b": {
                "max_len_cap": coverage_b.get("cap", coverage_b["effective_max_len"]),
                "effective_max_len": coverage_b["effective_max_len"],
                "training_truncated_rows": coverage_b["summary"]["training_truncated_rows"],
                "adapter_sha256": adapter_b_sha256,
                "cact_sha256": cact_b_sha256,
            },
        },
        "train_comparison": compare(train_a, train_b),
        "heldout_comparison": compare(heldout_a, heldout_b),
    }


def markdown(receipt: dict) -> str:
    train = receipt["train_comparison"]
    held = receipt["heldout_comparison"]
    return "\n".join([
        "# Needle deterministic max-len A/B",
        "",
        f"- Seed: {receipt['config']['seed']}",
        f"- Arm A cap/effective: {receipt['arms']['a']['max_len_cap']} / {receipt['arms']['a']['effective_max_len']}",
        f"- Arm B cap/effective: {receipt['arms']['b']['max_len_cap']} / {receipt['arms']['b']['effective_max_len']}",
        f"- Arm A truncated training rows: {receipt['arms']['a']['training_truncated_rows']}",
        f"- Arm B truncated training rows: {receipt['arms']['b']['training_truncated_rows']}",
        f"- Train A accuracy: {train['base']['overall_accuracy']}",
        f"- Train B accuracy: {train['tuned']['overall_accuracy']}",
        f"- Train delta B-A: {train['delta']['overall_accuracy']}",
        f"- Held-out A accuracy: {held['base']['overall_accuracy']}",
        f"- Held-out B accuracy: {held['tuned']['overall_accuracy']}",
        f"- Held-out delta B-A: {held['delta']['overall_accuracy']}",
        "",
        "A successful workflow proves execution of the specified paired experiment, not generalization.",
        "",
    ])


def main() -> None:
    p = argparse.ArgumentParser()
    for name in ["train-a", "train-b", "heldout-a", "heldout-b", "coverage-a", "coverage-b", "adapter-a", "adapter-b", "cact-a", "cact-b"]:
        p.add_argument("--" + name, required=True)
    p.add_argument("--seed", required=True, type=int)
    p.add_argument("--output", required=True)
    p.add_argument("--markdown", required=True)
    args = p.parse_args()
    receipt = build_receipt(
        train_a=load_jsonl(pathlib.Path(args.train_a)),
        train_b=load_jsonl(pathlib.Path(args.train_b)),
        heldout_a=load_jsonl(pathlib.Path(args.heldout_a)),
        heldout_b=load_jsonl(pathlib.Path(args.heldout_b)),
        coverage_a=json.load(open(args.coverage_a)),
        coverage_b=json.load(open(args.coverage_b)),
        adapter_a_sha256=sha256(pathlib.Path(args.adapter_a)),
        adapter_b_sha256=sha256(pathlib.Path(args.adapter_b)),
        cact_a_sha256=sha256(pathlib.Path(args.cact_a)),
        cact_b_sha256=sha256(pathlib.Path(args.cact_b)),
        seed=args.seed,
    )
    pathlib.Path(args.output).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    pathlib.Path(args.markdown).write_text(markdown(receipt))


if __name__ == "__main__":
    main()
