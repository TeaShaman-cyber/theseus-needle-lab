#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from needle_watch.git_state import publish_generated_receipt


def main() -> int:
    target_ref = os.environ.get("NEEDLE_WATCH_TARGET_REF")
    if not target_ref:
        print("NEEDLE_WATCH_PUBLISH ERROR missing NEEDLE_WATCH_TARGET_REF", file=sys.stderr)
        return 2
    published = publish_generated_receipt(PROJECT_ROOT, target_ref=target_ref)
    if published:
        print(f"NEEDLE_WATCH_PUBLISH SUCCESS target_ref={target_ref} commit={published}")
    else:
        print(f"NEEDLE_WATCH_PUBLISH NO_CHANGES target_ref={target_ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
