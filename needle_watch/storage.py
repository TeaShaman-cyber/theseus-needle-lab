from __future__ import annotations

import json
from pathlib import Path


def load_prior_candidate_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        item["candidate_id"]
        for item in payload.get("candidates", [])
        if isinstance(item, dict) and isinstance(item.get("candidate_id"), str)
    }


def load_prior_entity_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        item["source_entity_id"]
        for item in payload.get("candidates", [])
        if isinstance(item, dict) and isinstance(item.get("source_entity_id"), str)
    }


def write_receipt_snapshot(
    receipt: dict,
    *,
    repo_root: Path,
    date_key: str,
) -> tuple[Path, Path, Path]:
    data = (json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    run_id = receipt["run_id"]
    if not isinstance(run_id, str) or not run_id or Path(run_id).name != run_id:
        raise ValueError("run_id must be a path-safe non-empty string")
    run = repo_root / "data" / "runs" / f"{run_id}.json"
    daily = repo_root / "data" / "daily" / f"{date_key}.json"
    latest = repo_root / "data" / "latest" / "needle-watch.json"
    run.parent.mkdir(parents=True, exist_ok=True)
    daily.parent.mkdir(parents=True, exist_ok=True)
    latest.parent.mkdir(parents=True, exist_ok=True)
    if run.exists() and run.read_bytes() != data:
        raise ValueError(f"immutable run receipt already exists with different bytes: {run}")
    run.write_bytes(data)
    daily.write_bytes(data)
    latest.write_bytes(data)
    return run, daily, latest
