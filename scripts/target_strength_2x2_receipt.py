#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from compare_policy_eval import score, shared_max_new_tokens

ARM_CONFIG = {
    "A": {"target_representation": "reasoning_plus_tool_call", "epochs": 1},
    "B": {"target_representation": "reasoning_plus_tool_call", "epochs": 3},
    "C": {"target_representation": "tool_call_only", "epochs": 1},
    "D": {"target_representation": "tool_call_only", "epochs": 3},
}


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metric(scores: dict, arm: str, key: str):
    return scores[arm].get(key)


def _diff(a, b):
    if a is None or b is None:
        return None
    return b - a


def _effects(scores: dict, key: str) -> dict:
    a, b, c, d = (_metric(scores, arm, key) for arm in "ABCD")
    strength_reasoning = _diff(a, b)
    encoding_1 = _diff(a, c)
    strength_tool = _diff(c, d)
    encoding_3 = _diff(b, d)
    interaction = None
    if strength_reasoning is not None and strength_tool is not None:
        interaction = strength_tool - strength_reasoning
    return {
        "strength_with_reasoning": strength_reasoning,
        "encoding_at_1_epoch": encoding_1,
        "strength_tool_call_only": strength_tool,
        "encoding_at_3_epochs": encoding_3,
        "interaction_difference_of_differences": interaction,
    }


def _prediction_vector(rows: list[dict]) -> list[dict]:
    return [{"id": row["id"], "expected": row["expected"], "predicted": row["predicted"], "correct": bool(row["correct"])} for row in rows]


def build_receipt(
    *,
    arms: dict,
    source_dataset_sha256: str,
    derived_dataset_sha256: str,
    artifact_sha256: dict,
    seed: int,
) -> dict:
    train_scores = {arm: score(arms[arm]["train"]) for arm in ARM_CONFIG}
    heldout_scores = {arm: score(arms[arm]["heldout"]) for arm in ARM_CONFIG}
    budgets = {
        shared_max_new_tokens(arms[arm]["train"], arms[arm]["heldout"])
        for arm in ARM_CONFIG
    }
    if len(budgets) != 1:
        raise ValueError(f"mixed max_new_tokens across arms: {sorted(budgets)}")
    max_new_tokens = next(iter(budgets))

    arm_receipts = {}
    for arm, cfg in ARM_CONFIG.items():
        arm_receipts[arm] = {
            **cfg,
            "adapter_sha256": artifact_sha256[arm]["adapter"],
            "cact_sha256": artifact_sha256[arm]["cact"],
            "train": train_scores[arm],
            "heldout": heldout_scores[arm],
            "train_prediction_vector": _prediction_vector(arms[arm]["train"]),
        }

    return {
        "schema": "theseus.needle.target_strength_2x2.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "repository": os.environ.get("GITHUB_REPOSITORY"),
            "commit": os.environ.get("GITHUB_SHA"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "parent_issue": 10,
            "cactus_needle_version": "2.0.8",
            "upstream_reference": "cactus-compute/needle@ee221ce7c13579d9809209b979a9b7a50936614c",
        },
        "config": {
            "seed": int(seed),
            "batch_size": 2,
            "lr": 1e-4,
            "lora_rank": 4,
            "lora_alpha": 32.0,
            "max_len_cap": 1024,
            "export_bits": 4,
            "max_new_tokens": max_new_tokens,
        },
        "datasets": {
            "source_sha256": source_dataset_sha256,
            "tool_call_only_sha256": derived_dataset_sha256,
            "derivation": "remove_reasoning_field_only",
        },
        "arms": arm_receipts,
        "factor_effects": {
            "train_overall_accuracy": _effects(train_scores, "overall_accuracy"),
            "heldout_overall_accuracy": _effects(heldout_scores, "overall_accuracy"),
            "heldout_routing_accuracy": _effects(heldout_scores, "routing_accuracy"),
        },
        "interpretation_boundary": "descriptive_effects_not_statistical_significance",
    }


def load_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def markdown(receipt: dict) -> str:
    lines = ["# Needle target × strength 2×2 result", ""]
    for arm in "ABCD":
        data = receipt["arms"][arm]
        lines.append(
            f"- {arm}: {data['target_representation']}, epochs={data['epochs']}, "
            f"train={data['train']['overall_accuracy']:.3f}, heldout={data['heldout']['overall_accuracy']:.3f}"
        )
    lines += ["", "Descriptive effects only; this four-arm microexperiment does not establish statistical significance or generalization."]
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    for arm in "abcd":
        p.add_argument(f"--train-{arm}", required=True)
        p.add_argument(f"--heldout-{arm}", required=True)
        p.add_argument(f"--adapter-{arm}", required=True)
        p.add_argument(f"--cact-{arm}", required=True)
    p.add_argument("--source-dataset", required=True)
    p.add_argument("--derived-dataset", required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--markdown", required=True)
    args = p.parse_args()

    arms = {}
    artifacts = {}
    for upper, lower in zip("ABCD", "abcd"):
        arms[upper] = {
            "train": load_jsonl(pathlib.Path(getattr(args, f"train_{lower}"))),
            "heldout": load_jsonl(pathlib.Path(getattr(args, f"heldout_{lower}"))),
        }
        artifacts[upper] = {
            "adapter": sha256(pathlib.Path(getattr(args, f"adapter_{lower}"))),
            "cact": sha256(pathlib.Path(getattr(args, f"cact_{lower}"))),
        }

    receipt = build_receipt(
        arms=arms,
        source_dataset_sha256=sha256(pathlib.Path(args.source_dataset)),
        derived_dataset_sha256=sha256(pathlib.Path(args.derived_dataset)),
        artifact_sha256=artifacts,
        seed=args.seed,
    )
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    pathlib.Path(args.markdown).write_text(markdown(receipt))


if __name__ == "__main__":
    main()
