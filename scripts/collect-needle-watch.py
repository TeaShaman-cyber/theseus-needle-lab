#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from needle_watch.github_source import collect_github_queries, load_watch_config
from needle_watch.receipt import build_receipt, validate_receipt
from needle_watch.storage import (
    load_prior_candidate_ids,
    load_prior_entity_ids,
    write_receipt_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Needle Watch discovery receipts")
    parser.add_argument("--repo-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "config" / "needle-watch.json"
    )
    parser.add_argument("--fixture-source", type=Path)
    return parser.parse_args()


def parse_now() -> datetime:
    value = os.environ.get("NEEDLE_WATCH_NOW")
    if value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_source_data(args: argparse.Namespace, observed_at: str, since_date: str):
    if args.fixture_source:
        payload = json.loads(args.fixture_source.read_text(encoding="utf-8"))
        return payload.get("candidates", []), payload.get("source_health", [])
    config = load_watch_config(args.config)
    return collect_github_queries(
        config,
        token=os.environ.get("GITHUB_TOKEN"),
        observed_at=observed_at,
        since_date=since_date,
    )


def main() -> int:
    args = parse_args()
    now = parse_now()
    window_start_dt = now - timedelta(days=1)
    observed_at = iso_z(now)
    window_start = iso_z(window_start_dt)
    window_end = observed_at
    date_key = now.date().isoformat()
    since_date = window_start

    prior_path = args.repo_root / "data" / "latest" / "needle-watch.json"
    prior_ids = load_prior_candidate_ids(prior_path)
    prior_entity_ids = load_prior_entity_ids(prior_path)
    candidates, source_health = load_source_data(args, observed_at, since_date)

    run_id = (
        os.environ.get("NEEDLE_WATCH_RUN_ID")
        or os.environ.get("GITHUB_RUN_ID")
        or f"local-{now.strftime('%Y%m%dT%H%M%SZ')}"
    )
    collector_revision = (
        os.environ.get("NEEDLE_WATCH_COLLECTOR_REVISION")
        or os.environ.get("GITHUB_SHA")
        or "unknown"
    )
    receipt = build_receipt(
        run_id=run_id,
        generated_at=observed_at,
        window_start=window_start,
        window_end=window_end,
        collector_revision=collector_revision,
        source_health=source_health,
        candidates=candidates,
        prior_ids=prior_ids,
        prior_entity_ids=prior_entity_ids,
    )
    errors = validate_receipt(receipt)
    if errors:
        for error in errors:
            print(f"NEEDLE_WATCH_RECEIPT ERROR {error}", file=sys.stderr)
        return 2

    run, daily, latest = write_receipt_snapshot(receipt, repo_root=args.repo_root, date_key=date_key)
    print(
        "NEEDLE_WATCH_RECEIPT PASS "
        f"run_id={run_id} candidates={len(receipt['candidates'])} "
        f"sources={len(receipt['source_health'])} run={run} daily={daily} latest={latest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
