from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import pathlib

EXPECTED_NEEDLE_VERSION = "2.0.8"


def audit_examples(rows, tokenizer, render, max_len: int) -> dict:
    audited = []
    truncated = []
    for row in rows:
        case_id = row["case_id"]
        example = row.get("example", row)
        prompt, target = render(example)
        prompt_tokens = len(tokenizer.encode(prompt))
        target_tokens = len(tokenizer.encode(target))
        total_tokens = 1 + prompt_tokens + target_tokens + 1  # BOS + content + EOS
        eos_retained = total_tokens <= max_len
        item = {
            "case_id": case_id,
            "prompt_tokens": prompt_tokens,
            "target_tokens": target_tokens,
            "total_tokens": total_tokens,
            "max_len": max_len,
            "eos_retained": eos_retained,
            "target_fully_retained": eos_retained,
        }
        audited.append(item)
        if not eos_retained:
            truncated.append(case_id)
    return {
        "rows": audited,
        "row_count": len(audited),
        "max_observed_tokens": max((r["total_tokens"] for r in audited), default=0),
        "truncated_case_ids": truncated,
        "status": "VERIFIED_ZERO_TRUNCATION" if not truncated else "FAIL_TARGET_TRUNCATION",
    }


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def runtime_audit(train_path: pathlib.Path, semantic_path: pathlib.Path, max_len: int) -> dict:
    from needle.model.finetune import render_example
    from needle.model.tokenizer import get_tokenizer

    version = importlib.metadata.version("cactus-needle")
    if version != EXPECTED_NEEDLE_VERSION:
        raise RuntimeError(f"RUNTIME_DRIFT: cactus-needle={version} expected={EXPECTED_NEEDLE_VERSION}")

    examples = _load_jsonl(train_path)
    semantic = [r for r in _load_jsonl(semantic_path) if r["split"] == "train"]
    if len(examples) != len(semantic):
        raise RuntimeError("DATASET_ALIGNMENT_FAILED: train projection/source row count differs")
    rows = [{"case_id": source["case_id"], "example": example} for source, example in zip(semantic, examples)]

    tokenizer = get_tokenizer()
    result = audit_examples(rows, tokenizer, render_example, max_len)
    model_path = pathlib.Path(tokenizer.model_path)
    result["runtime"] = {
        "cactus_needle": version,
        "tokenizer_model_path": str(model_path),
        "tokenizer_model_sha256": _sha256(model_path),
        "tokenizer_md5": tokenizer.md5,
    }
    result["inputs"] = {
        "train_sha256": _sha256(train_path),
        "semantic_source_sha256": _sha256(semantic_path),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=pathlib.Path, default=pathlib.Path("experiments/needle-realistic-sft/data/train.needle.jsonl"))
    parser.add_argument("--semantic", type=pathlib.Path, default=pathlib.Path("experiments/needle-realistic-sft/source/semantic-cases.jsonl"))
    parser.add_argument("--max-len", type=int, default=256)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    result = runtime_audit(args.train, args.semantic, args.max_len)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "row_count", "max_observed_tokens", "truncated_case_ids")}, sort_keys=True))
    return 0 if result["status"] == "VERIFIED_ZERO_TRUNCATION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
