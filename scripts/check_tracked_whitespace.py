#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path


def find_violations(paths: list[Path]) -> list[tuple[str, int, bytes]]:
    violations: list[tuple[str, int, bytes]] = []
    for path in paths:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data:
            continue
        for line_number, line in enumerate(data.splitlines(), 1):
            stripped = line.rstrip(b" \t")
            suffix = line[len(stripped):]
            if not suffix:
                continue
            # Markdown uses exactly two trailing spaces as an intentional hard line break.
            if path.suffix.lower() == ".md" and suffix == b"  ":
                continue
            violations.append((path.as_posix(), line_number, suffix))
    return violations


def tracked_paths() -> list[Path]:
    raw = subprocess.check_output(["git", "ls-files", "-z"])
    return [Path(name) for name in raw.decode("utf-8").split("\0") if name]


def main() -> int:
    violations = find_violations(tracked_paths())
    if not violations:
        print("QA_TRACKED_WHITESPACE_PASS")
        return 0
    for path, line_number, suffix in violations:
        print(
            f"QA_TRACKED_WHITESPACE_ERROR: {path}:{line_number}: trailing={suffix!r}"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
