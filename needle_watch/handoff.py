from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from needle_watch.receipt import validate_receipt
from needle_watch.storage import write_receipt_snapshot

MAX_HANDOFF_BYTES = 65_536


def _receipt_paths(repo_root: Path, receipt: dict) -> tuple[Path, Path, Path]:
    run_id = receipt.get("run_id")
    generated_at = receipt.get("generated_at")
    if not isinstance(run_id, str) or not run_id or Path(run_id).name != run_id:
        raise ValueError("receipt run_id is not path-safe")
    if not isinstance(generated_at, str):
        raise ValueError("receipt generated_at is invalid")
    try:
        parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("receipt generated_at is invalid") from exc
    date_key = parsed.date().isoformat()
    return (
        repo_root / "data" / "runs" / f"{run_id}.json",
        repo_root / "data" / "daily" / f"{date_key}.json",
        repo_root / "data" / "latest" / "needle-watch.json",
    )


def _validate(receipt: dict) -> None:
    errors = validate_receipt(receipt)
    if errors:
        raise ValueError("invalid receipt: " + "; ".join(errors))


def _compact_payload(receipt: dict) -> str:
    return json.dumps(
        receipt,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    )


def _enforce_size(payload: str) -> bytes:
    data = payload.encode("utf-8")
    if len(data) > MAX_HANDOFF_BYTES:
        raise ValueError(
            f"receipt handoff exceeds size limit: {len(data)} > {MAX_HANDOFF_BYTES}"
        )
    return data


def export_receipt_handoff(repo_root: Path) -> tuple[str, str]:
    latest = repo_root / "data" / "latest" / "needle-watch.json"
    receipt = json.loads(latest.read_text(encoding="utf-8"))
    _validate(receipt)
    run, daily, latest = _receipt_paths(repo_root, receipt)
    raw_views = [path.read_bytes() for path in (run, daily, latest)]
    if len(set(raw_views)) != 1:
        raise ValueError("snapshot bytes differ across run, daily, and latest views")
    payload = _compact_payload(receipt)
    data = _enforce_size(payload)
    return payload, hashlib.sha256(data).hexdigest()


def import_receipt_handoff(
    repo_root: Path,
    payload: str,
    expected_digest: str,
) -> tuple[Path, Path, Path]:
    data = _enforce_size(payload)
    actual_digest = hashlib.sha256(data).hexdigest()
    if actual_digest != expected_digest:
        raise ValueError("receipt handoff digest mismatch")
    receipt = json.loads(payload)
    if not isinstance(receipt, dict):
        raise ValueError("receipt handoff must contain a JSON object")
    _validate(receipt)
    generated_at = receipt.get("generated_at")
    if not isinstance(generated_at, str):
        raise ValueError("receipt generated_at is invalid")
    try:
        date_key = datetime.fromisoformat(
            generated_at.replace("Z", "+00:00")
        ).date().isoformat()
    except ValueError as exc:
        raise ValueError("receipt generated_at is invalid") from exc
    return write_receipt_snapshot(receipt, repo_root=repo_root, date_key=date_key)
