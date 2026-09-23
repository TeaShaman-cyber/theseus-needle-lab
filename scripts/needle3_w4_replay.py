from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import time
from typing import Any

import needle3_deployment_canary as canary

SCHEMA = "theseus.needle3.w4_replay_receipt.v1"
W4_SURFACE = "lora_w4_reference"


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def w4_result_rows(cases, responses):
    if len(cases) != len(responses):
        raise ValueError("surface response count mismatch")
    rows = []
    for case, (response, latency_ms) in zip(cases, responses):
        predicted = canary.classify_response(response)
        rows.append({
            "schema_version": canary.RESULT_SCHEMA,
            "surface": W4_SURFACE,
            "case_id": case["case_id"],
            "family_id": case["family_id"],
            "category": case["category"],
            "expected": case["expected"],
            "source_kind": case["source_kind"],
            "case_input_sha256": canary.case_input_sha256(case),
            "predicted": predicted,
            "correct": predicted == case["expected"],
            "latency_ms": latency_ms,
            "response": response,
        })
    return rows


def validate_w4_rows(cases, rows):
    if [r.get("case_id") for r in rows] != [c["case_id"] for c in cases]:
        raise ValueError("W4 result case order mismatch")
    for case, row in zip(cases, rows):
        if row.get("schema_version") != canary.RESULT_SCHEMA:
            raise ValueError("W4 result schema mismatch")
        if row.get("surface") != W4_SURFACE:
            raise ValueError("W4 result surface mismatch")
        for field in ("family_id", "category", "expected", "source_kind"):
            if row.get(field) != case[field]:
                raise ValueError("W4 result fixture projection mismatch")
        if row.get("case_input_sha256") != canary.case_input_sha256(case):
            raise ValueError("W4 result input binding mismatch")
        if row.get("predicted") not in canary.ALLOWED_PREDICTIONS:
            raise ValueError("invalid W4 prediction")
        if bool(row.get("correct")) != (row["predicted"] == row["expected"]):
            raise ValueError("W4 correct flag mismatch")
        if canary.classify_response(row.get("response") or {}) != row["predicted"]:
            raise ValueError("W4 prediction/raw response mismatch")
    return rows


def run_w4(args):
    manifest = canary.load_json(args.manifest)
    cases = canary.validate_manifest(manifest, args.manifest)
    canary.verify_installed_package(manifest)

    from needle.model.architecture import SimpleAttentionNetwork
    from needle.model.checkpoints import read_adapter
    from needle.model.finetune import merge_lora
    from needle.model.quantize import WEIGHT_BITS, cq_ste_params
    from needle.model.run import build_prompt, generate, load_checkpoint
    from needle.model.tokenizer import get_tokenizer

    params, config = load_checkpoint(str(args.checkpoint))
    adapter = read_adapter(str(args.lora))
    lora = {
        tuple(key.split("/")): {"A": value["A"], "B": value["B"]}
        for key, value in adapter["lora"].items()
    }
    params = merge_lora(params, lora, adapter["scale"])
    params = cq_ste_params(params, WEIGHT_BITS)

    model = SimpleAttentionNetwork(config)
    tokenizer = get_tokenizer(config.vocab_size)
    responses = []
    for case in cases:
        prompt = build_prompt(case["query"], case["tools"])
        started = time.perf_counter()
        text = generate(
            model, params, tokenizer, prompt,
            max_new_tokens=args.max_new_tokens,
            temperature=0.0, seed=0, stream=False,
        )
        latency = (time.perf_counter() - started) * 1000.0
        responses.append((canary.reference_text_to_response(text), latency))
    canary.write_jsonl(args.output, w4_result_rows(cases, responses))
    return 0


def diagnostic_label(float_vs_w4, w4_vs_built):
    if w4_vs_built["prediction_mismatch_count"] == 0:
        return "W4_PREDICTIONS_MATCH_BUILT"
    if w4_vs_built["prediction_mismatch_count"] < float_vs_w4["prediction_mismatch_count"]:
        return "W4_REDUCES_DIVERGENCE"
    return "W4_DOES_NOT_EXPLAIN_BUILT_DIVERGENCE"


def compare(args):
    manifest = canary.load_json(args.manifest)
    cases = canary.validate_manifest(manifest, args.manifest)
    float_rows = canary.validate_surface_rows(
        cases, canary.load_jsonl(args.float_results), "lora_reference"
    )
    built_rows = canary.validate_surface_rows(
        cases, canary.load_jsonl(args.built_results), "built_cact"
    )
    w4_rows = validate_w4_rows(cases, canary.load_jsonl(args.w4_results))

    source_provenance = canary.load_json(args.source_provenance)
    observed_adapter = sha256_file(args.lora)
    observed_base = sha256_file(args.checkpoint)
    if source_provenance.get("lora_adapter_sha256") != observed_adapter:
        raise ValueError("source adapter identity mismatch")
    if source_provenance.get("base_checkpoint_sha256") != observed_base:
        raise ValueError("source base checkpoint identity mismatch")

    float_vs_w4 = canary.pairwise_divergence(float_rows, w4_rows)
    w4_vs_built = canary.pairwise_divergence(w4_rows, built_rows)
    float_vs_built = canary.pairwise_divergence(float_rows, built_rows)
    receipt = {
        "schema_version": SCHEMA,
        "source_run_id": args.source_run_id,
        "source_run_attempt": args.source_run_attempt,
        "source_experiment_sha": args.source_experiment_sha,
        "replay_experiment_sha": args.replay_experiment_sha,
        "base_checkpoint_sha256": observed_base,
        "lora_adapter_sha256": observed_adapter,
        "metrics": {
            "lora_reference_float": canary.surface_metrics(float_rows),
            "lora_w4_reference": canary.surface_metrics(w4_rows),
            "built_cact": canary.surface_metrics(built_rows),
        },
        "float_lora_vs_w4_lora": float_vs_w4,
        "w4_lora_vs_built_cact": w4_vs_built,
        "float_lora_vs_built_cact": float_vs_built,
        "diagnostic": diagnostic_label(float_vs_w4, w4_vs_built),
        "interpretation_boundary": (
            "diagnostic_prediction_geometry_only_not_general_model_quality_or_authority"
        ),
    }
    canary.write_json(args.output, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


def validate_receipt(args):
    rebuilt = args.output.parent / ".w4-rebuilt.json"
    clone = argparse.Namespace(**vars(args))
    clone.output = rebuilt
    compare(clone)
    if canary.load_json(args.output) != canary.load_json(rebuilt):
        raise ValueError("W4 replay receipt does not match rebuilt evidence")
    rebuilt.unlink()
    print("NEEDLE3_W4_REPLAY_READBACK_PASS")
    return 0


def parser():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=pathlib.Path, default=canary.DEFAULT_MANIFEST)
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run-w4")
    run.add_argument("--checkpoint", type=pathlib.Path, required=True)
    run.add_argument("--lora", type=pathlib.Path, required=True)
    run.add_argument("--max-new-tokens", type=int, default=128)
    run.add_argument("--output", type=pathlib.Path, required=True)
    run.set_defaults(func=run_w4)

    for name, func in (("compare", compare), ("validate-receipt", validate_receipt)):
        q = sub.add_parser(name)
        q.add_argument("--float-results", type=pathlib.Path, required=True)
        q.add_argument("--w4-results", type=pathlib.Path, required=True)
        q.add_argument("--built-results", type=pathlib.Path, required=True)
        q.add_argument("--source-provenance", type=pathlib.Path, required=True)
        q.add_argument("--lora", type=pathlib.Path, required=True)
        q.add_argument("--checkpoint", type=pathlib.Path, required=True)
        q.add_argument("--source-run-id", required=True)
        q.add_argument("--source-run-attempt", required=True)
        q.add_argument("--source-experiment-sha", required=True)
        q.add_argument("--replay-experiment-sha", required=True)
        q.add_argument("--output", type=pathlib.Path, required=True)
        q.set_defaults(func=func)
    return p


def main():
    args = parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
