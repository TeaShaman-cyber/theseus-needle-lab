#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import json
import pathlib


def load(path):
    return [json.loads(line) for line in pathlib.Path(path).read_text().splitlines() if line.strip()]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def summarize(rows):
    n = len(rows)
    valid = sum(bool(r.get("valid_route_call")) for r in rows)
    correct = sum(bool(r.get("correct")) for r in rows)
    return {
        "n": n,
        "valid_calls": valid,
        "valid_call_rate": valid / n if n else None,
        "correct": correct,
        "decision_accuracy": correct / n if n else None,
        "prediction_vector": [{"id":r["id"], "expected":r["expected"], "predicted":r["predicted"], "valid_route_call":bool(r.get("valid_route_call")), "correct":bool(r.get("correct"))} for r in rows],
    }


def build_receipt(train_base, train_old, train_new, held_base, held_old, held_new, *, source_sha256, corrected_sha256, old_cact_sha256, corrected_adapter_sha256, corrected_cact_sha256):
    train = {"base": summarize(train_base), "old_tuned": summarize(train_old), "corrected_tuned": summarize(train_new)}
    held = {"base": summarize(held_base), "old_tuned": summarize(held_old), "corrected_tuned": summarize(held_new)}
    return {
        "schema": "theseus.needle.corrected_contract_ab.v1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "training_contract": "described_route_plus_explicit_classification_prefix",
        "evaluation_contract": "all_models_use_same_corrected_framing",
        "inputs": {
            "source_dataset_sha256": source_sha256,
            "corrected_dataset_sha256": corrected_sha256,
            "frozen_old_control_cact_sha256": old_cact_sha256,
            "corrected_adapter_sha256": corrected_adapter_sha256,
            "corrected_cact_sha256": corrected_cact_sha256,
        },
        "train": train,
        "heldout": held,
        "effects": {
            "corrected_minus_old_train_call_rate": train["corrected_tuned"]["valid_call_rate"] - train["old_tuned"]["valid_call_rate"],
            "corrected_minus_old_train_accuracy": train["corrected_tuned"]["decision_accuracy"] - train["old_tuned"]["decision_accuracy"],
            "corrected_minus_old_heldout_call_rate": held["corrected_tuned"]["valid_call_rate"] - held["old_tuned"]["valid_call_rate"],
            "corrected_minus_old_heldout_accuracy": held["corrected_tuned"]["decision_accuracy"] - held["old_tuned"]["decision_accuracy"],
        },
        "interpretation_boundary": "bounded_single_corrected_training_run_not_statistical_significance",
    }


def main():
    p = argparse.ArgumentParser()
    for scope in ("train", "heldout"):
        for model in ("base", "old", "new"):
            p.add_argument(f"--{scope}-{model}", required=True)
    p.add_argument("--source-dataset", required=True)
    p.add_argument("--corrected-dataset", required=True)
    p.add_argument("--old-cact", required=True)
    p.add_argument("--corrected-adapter", required=True)
    p.add_argument("--corrected-cact", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--markdown", required=True)
    a = p.parse_args()
    r = build_receipt(
        load(a.train_base), load(a.train_old), load(a.train_new),
        load(a.heldout_base), load(a.heldout_old), load(a.heldout_new),
        source_sha256=sha256(a.source_dataset), corrected_sha256=sha256(a.corrected_dataset),
        old_cact_sha256=sha256(a.old_cact), corrected_adapter_sha256=sha256(a.corrected_adapter), corrected_cact_sha256=sha256(a.corrected_cact),
    )
    pathlib.Path(a.output).write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    md = ["# Corrected contract A/B", ""]
    for scope in ("train", "heldout"):
        md.append(f"## {scope}")
        for model in ("base", "old_tuned", "corrected_tuned"):
            s = r[scope][model]
            md.append(f"- {model}: calls {s['valid_calls']}/{s['n']} ({s['valid_call_rate']:.3f}), correct {s['correct']}/{s['n']} ({s['decision_accuracy']:.3f})")
        md.append("")
    md.append("## effects")
    for k,v in r["effects"].items():
        md.append(f"- {k}: {v:+.3f}")
    pathlib.Path(a.markdown).write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
