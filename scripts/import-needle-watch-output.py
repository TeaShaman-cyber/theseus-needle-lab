#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from needle_watch.handoff import import_receipt_handoff


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Needle Watch receipt from GitHub job outputs")
    parser.add_argument("--repo-root", type=Path, default=PROJECT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = os.environ.get("NEEDLE_WATCH_RECEIPT_JSON")
    digest = os.environ.get("NEEDLE_WATCH_RECEIPT_SHA256")
    if not payload or not digest:
        print("NEEDLE_WATCH_HANDOFF ERROR missing receipt job output", file=sys.stderr)
        return 2
    try:
        run, daily, latest = import_receipt_handoff(args.repo_root, payload, digest)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"NEEDLE_WATCH_HANDOFF ERROR {exc}", file=sys.stderr)
        return 2
    print(
        "NEEDLE_WATCH_HANDOFF IMPORT PASS "
        f"run={run} daily={daily} latest={latest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
