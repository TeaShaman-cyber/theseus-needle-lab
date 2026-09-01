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


def write_receipt_snapshot(
    receipt: dict,
    *,
    repo_root: Path,
    date_key: str,
) -> tuple[Path, Path]:
    data = (json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    dated = repo_root / "data" / date_key / "needle-watch.json"
    latest = repo_root / "data" / "latest" / "needle-watch.json"
    dated.parent.mkdir(parents=True, exist_ok=True)
    latest.parent.mkdir(parents=True, exist_ok=True)
    dated.write_bytes(data)
    latest.write_bytes(data)
    return dated, latest
