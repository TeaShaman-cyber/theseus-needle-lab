#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
from datetime import datetime, timezone


def _comparison_module():
    path = pathlib.Path(__file__).with_name("compare_policy_eval.py")
    spec = importlib.util.spec_from_file_location("_needle_compare_policy_eval", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def build_receipt(
    mixed: list[dict],
    w4: list[dict],
    *,
    checkpoint_sha256: str,
    adapter_sha256: str,
    mixed_sha256: str,
    w4_sha256: str,
    w4_size_bytes: int,
) -> dict:
    compare_module = _comparison_module()
    comparison = compare_module.compare(mixed, w4)
    max_new_tokens = compare_module.shared_max_new_tokens(mixed, w4)
    return {
        "schema": "theseus.needle.quantization_probe.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "same_adapter_default_mixed_vs_uniform_w4_train_replay",
        "models": {
            "base_field": "default_mixed",
            "tuned_field": "uniform_w4",
        },
        "source": {
            "repository": os.environ.get("GITHUB_REPOSITORY"),
            "commit": os.environ.get("GITHUB_SHA"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "source_smoke_run_id": "33319821037",
            "source_smoke_commit": "9a9b4bf1083a4fe2f8f732f779ede008ab1c3b75",
        },
        "inputs": {
            "checkpoint_sha256": checkpoint_sha256,
            "adapter_sha256": adapter_sha256,
            "default_mixed_cact_sha256": mixed_sha256,
            "uniform_w4_cact_sha256": w4_sha256,
            "uniform_w4_cact_size_bytes": int(w4_size_bytes),
            "max_new_tokens": max_new_tokens,
            "build_bits": 4,
        },
        "comparison": comparison,
    }


def markdown(receipt: dict) -> str:
    comparison = receipt["comparison"]
    left = comparison["base"]
    right = comparison["tuned"]
    delta = comparison["delta"]
    return f"""# Needle quantization probe

- Default mixed train accuracy: {left['overall_accuracy']:.3f}
- Uniform W4 train accuracy: {right['overall_accuracy']:.3f}
- Delta: {delta['overall_accuracy']:+.3f}
- Default mixed routing accuracy: {left['routing_accuracy']:.3f}
- Uniform W4 routing accuracy: {right['routing_accuracy']:.3f}
- Changed predictions: {len(comparison['changed_predictions'])}
- W4 artifact SHA-256: `{receipt['inputs']['uniform_w4_cact_sha256']}`
- W4 artifact size: {receipt['inputs']['uniform_w4_cact_size_bytes']} bytes

This probe changes export quantization only. It does not retrain the adapter.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mixed", required=True)
    parser.add_argument("--w4", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--mixed-artifact", required=True)
    parser.add_argument("--w4-artifact", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown", required=True)
    args = parser.parse_args()

    mixed_path = pathlib.Path(args.mixed)
    w4_path = pathlib.Path(args.w4)
    checkpoint_path = pathlib.Path(args.checkpoint)
    adapter_path = pathlib.Path(args.adapter)
    mixed_artifact_path = pathlib.Path(args.mixed_artifact)
    w4_artifact_path = pathlib.Path(args.w4_artifact)

    receipt = build_receipt(
        load_jsonl(mixed_path),
        load_jsonl(w4_path),
        checkpoint_sha256=sha256(checkpoint_path),
        adapter_sha256=sha256(adapter_path),
        mixed_sha256=sha256(mixed_artifact_path),
        w4_sha256=sha256(w4_artifact_path),
        w4_size_bytes=w4_artifact_path.stat().st_size,
    )
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    pathlib.Path(args.markdown).write_text(markdown(receipt))


if __name__ == "__main__":
    main()
