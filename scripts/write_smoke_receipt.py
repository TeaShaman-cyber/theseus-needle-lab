#!/usr/bin/env python3
import argparse
import hashlib
import importlib.metadata
import json
import os
import pathlib
import platform
import re
from datetime import datetime, timezone


def _duration_seconds(value: str) -> float:
    parts = value.strip().split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return float(value)


def parse_gnu_time(text: str) -> dict:
    result = {}
    wall = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*(\S+)", text)
    rss = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", text)
    if wall:
        result["wall_seconds"] = _duration_seconds(wall.group(1))
    if rss:
        result["peak_rss_kb"] = int(rss.group(1))
    return result


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(path: pathlib.Path) -> dict:
    if not path.exists():
        return {"path": str(path), "present": False}
    return {
        "path": str(path),
        "present": True,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _read_json(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _read_seconds(path: pathlib.Path) -> float | None:
    if not path.exists():
        return None
    text = path.read_text().strip()
    return float(text) if text else None


def _version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def build_receipt(args) -> dict:
    metrics_dir = pathlib.Path(args.metrics_dir)
    stages = {
        "install": {
            "outcome": os.environ.get("INSTALL_OUTCOME", "unknown"),
            "wall_seconds": _read_seconds(metrics_dir / "install.seconds"),
        },
        "checkpoint_download": {
            "outcome": os.environ.get("CHECKPOINT_OUTCOME", "unknown"),
            "wall_seconds": _read_seconds(metrics_dir / "checkpoint.seconds"),
        },
        "finetune": {
            "outcome": os.environ.get("FINETUNE_OUTCOME", "unknown"),
            **parse_gnu_time((metrics_dir / "finetune.time").read_text() if (metrics_dir / "finetune.time").exists() else ""),
        },
        "build": {
            "outcome": os.environ.get("BUILD_OUTCOME", "unknown"),
            **parse_gnu_time((metrics_dir / "build.time").read_text() if (metrics_dir / "build.time").exists() else ""),
        },
    }
    return {
        "schema": "theseus.needle.cpu_smoke.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "question": "Can a standard public GitHub-hosted ubuntu-latest runner complete real Needle 2 finetune -> build within the bounded CPU smoke?",
        "scope": "feasibility_only_not_model_quality",
        "source": {
            "repository": os.environ.get("GITHUB_REPOSITORY"),
            "commit": os.environ.get("GITHUB_SHA"),
            "ref": os.environ.get("GITHUB_REF"),
            "workflow": os.environ.get("GITHUB_WORKFLOW"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "needle_upstream_commit": "ee221ce7c13579d9809209b979a9b7a50936614c",
        },
        "runtime": {
            "runner_os": os.environ.get("RUNNER_OS"),
            "runner_arch": os.environ.get("RUNNER_ARCH"),
            "image_os": os.environ.get("ImageOS"),
            "image_version": os.environ.get("ImageVersion"),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
            **_read_json(metrics_dir / "runner.json"),
        },
        "packages": {
            "cactus-needle": _version("cactus-needle"),
            "jax": _version("jax"),
            "jaxlib": _version("jaxlib"),
            "flax": _version("flax"),
            "optax": _version("optax"),
            "numpy": _version("numpy"),
            "sentencepiece": _version("sentencepiece"),
            "huggingface-hub": _version("huggingface-hub"),
        },
        "config": {
            "examples": 12,
            "max_len": 128,
            "epochs": 1,
            "batch_size": 2,
            "lora_rank": 4,
            "generate_examples": 0,
            "openrouter_used": False,
            "secrets_required": False,
        },
        "stages": stages,
        "artifacts": {
            "dataset": _artifact(pathlib.Path(args.data)),
            "workflow": _artifact(pathlib.Path(args.workflow)),
            "checkpoint": _artifact(pathlib.Path(args.checkpoint)),
            "adapter": _artifact(pathlib.Path(args.adapter)),
            "tuned_cact": _artifact(pathlib.Path(args.cact)),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--metrics-dir", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--cact", required=True)
    args = parser.parse_args()
    receipt = build_receipt(args)
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
