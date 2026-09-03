from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re

WALL_LIMIT_SECONDS = 8 * 60
RSS_LIMIT_KB = 12 * 1024 * 1024
SCHEMA = "theseus.needle.realistic_sft_resource_dry_run.v2"


def _sha256(path: pathlib.Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _elapsed_seconds(value: str) -> float:
    parts = value.strip().split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    raise ValueError(f"unsupported GNU time elapsed value: {value}")


def parse_gnu_time(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    rss = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", text)
    elapsed = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*([^\n]+)", text)
    if not rss or not elapsed:
        raise ValueError("missing GNU time resource fields")
    return {"max_rss_kb": int(rss.group(1)), "elapsed_seconds": _elapsed_seconds(elapsed.group(1))}


def build_receipt(metrics: dict, *, token_audit_status: str) -> dict:
    preconditions_ok = token_audit_status == "VERIFIED_ZERO_TRUNCATION"
    execution_ok = int(metrics.get("exit_code", 1)) == 0 and int(metrics.get("disk_free_bytes_after", 0)) > 0
    resource_ok = (
        float(metrics.get("elapsed_seconds", float("inf"))) <= WALL_LIMIT_SECONDS
        and int(metrics.get("max_rss_kb", RSS_LIMIT_KB + 1)) <= RSS_LIMIT_KB
    )
    if not preconditions_ok:
        disposition = "BLOCKED_PRECONDITION"
    elif not execution_ok or not resource_ok:
        disposition = "BLOCKED_RESOURCE_ENVELOPE"
    else:
        disposition = "PASS_RESOURCE_GATE"
    return {
        "schema": SCHEMA,
        "interpretation_boundary": "resource_measurement_only_not_model_quality_evidence",
        "thresholds": {"wall_seconds_max": WALL_LIMIT_SECONDS, "max_rss_kb_max": RSS_LIMIT_KB},
        "token_audit_status": token_audit_status,
        "metrics": metrics,
        "disposition": disposition,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--time", type=pathlib.Path, required=True)
    p.add_argument("--exit-code", type=pathlib.Path, required=True)
    p.add_argument("--disk", type=pathlib.Path, required=True)
    p.add_argument("--token-audit", type=pathlib.Path, required=True)
    p.add_argument("--train", type=pathlib.Path, required=True)
    p.add_argument("--checkpoint", type=pathlib.Path, required=True)
    p.add_argument("--adapter", type=pathlib.Path, required=True)
    p.add_argument("--experiment-commit", required=True)
    p.add_argument("--launcher-commit", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--output", type=pathlib.Path, required=True)
    args = p.parse_args()

    metrics = parse_gnu_time(args.time)
    metrics["exit_code"] = int(args.exit_code.read_text().strip())
    disk = json.loads(args.disk.read_text())
    metrics.update(disk)
    audit = json.loads(args.token_audit.read_text())
    receipt = build_receipt(metrics, token_audit_status=audit["status"])
    receipt["source"] = {
        "experiment_commit": args.experiment_commit,
        "launcher_commit": args.launcher_commit,
        "workflow_run_id": args.run_id,
        "parent_issue": 26,
    }
    receipt["config"] = {
        "cactus_needle": "2.0.8", "seed": 0, "epochs": 1, "batch_size": 16,
        "lr": 1e-4, "lora_rank": 16, "lora_alpha": 32, "max_len": 256,
        "val_split": 0.1, "workers": 1,
    }
    receipt["inputs"] = {
        "train_sha256": _sha256(args.train),
        "checkpoint_sha256": _sha256(args.checkpoint),
        "tokenizer_model_sha256": audit["runtime"]["tokenizer_model_sha256"],
        "token_audit_max_observed_tokens": audit["max_observed_tokens"],
        "token_audit_truncated_case_ids": audit["truncated_case_ids"],
    }
    receipt["outputs"] = {"adapter_sha256": _sha256(args.adapter), "adapter_exists": args.adapter.is_file()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["disposition"] == "PASS_RESOURCE_GATE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
