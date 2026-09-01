#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from needle_watch.handoff import export_receipt_handoff


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Needle Watch receipt as GitHub job outputs")
    parser.add_argument("--repo-root", type=Path, default=PROJECT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print("NEEDLE_WATCH_HANDOFF ERROR missing GITHUB_OUTPUT", file=sys.stderr)
        return 2
    try:
        payload, digest = export_receipt_handoff(args.repo_root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"NEEDLE_WATCH_HANDOFF ERROR {exc}", file=sys.stderr)
        return 2
    data = payload.encode("utf-8")
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(f"receipt_json={payload}\n")
        handle.write(f"receipt_sha256={digest}\n")
        handle.write(f"receipt_bytes={len(data)}\n")
    print(
        "NEEDLE_WATCH_HANDOFF EXPORT PASS "
        f"bytes={len(data)} sha256={digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
