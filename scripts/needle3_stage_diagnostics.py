#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import resource
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Any


SCHEMA = "theseus.needle3.stage_diagnostics.v1"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def mem_available_kib() -> int | None:
    path = pathlib.Path("/proc/meminfo")
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            parts = line.split()
            if len(parts) >= 2:
                return int(parts[1])
    return None


def tree_size_kib(path: pathlib.Path) -> int:
    try:
        if path.is_symlink() or not path.exists():
            return 0
        if path.is_file():
            return (path.stat().st_size + 1023) // 1024
    except OSError:
        return 0

    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            for entry in current.iterdir():
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir():
                        stack.append(entry)
                    elif entry.is_file():
                        total += entry.stat().st_size
                except OSError:
                    continue
        except OSError:
            continue
    return (total + 1023) // 1024


def snapshot(tracked: list[pathlib.Path], started: float) -> dict[str, Any]:
    disk = shutil.disk_usage("/")
    return {
        "ts": utc_now(),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "mem_available_kib": mem_available_kib(),
        "root_free_kib": disk.free // 1024,
        "tracked_kib": {
            path.as_posix(): tree_size_kib(path)
            for path in tracked
        },
    }


def emit_heartbeat(stage: str, value: dict[str, Any]) -> None:
    tracked = ",".join(
        f"{name}:{size}"
        for name, size in sorted(value["tracked_kib"].items())
    )
    print(
        "needle3_stage_heartbeat "
        f"stage={stage} "
        f"ts={value['ts']} "
        f"elapsed_seconds={value['elapsed_seconds']} "
        f"mem_available_kib={value['mem_available_kib']} "
        f"root_free_kib={value['root_free_kib']} "
        f"tracked_kib={tracked}",
        flush=True,
    )


def _max_child_rss_kib() -> int:
    value = int(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    if sys.platform == "darwin":
        return value // 1024
    return value


def run(args: argparse.Namespace) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("STAGE_COMMAND_REQUIRED")
    if not args.stage or any(ch.isspace() for ch in args.stage):
        raise SystemExit("STAGE_NAME_INVALID")
    if args.interval_seconds <= 0:
        raise SystemExit("HEARTBEAT_INTERVAL_INVALID")

    tracked = [pathlib.Path(value) for value in args.track]
    args.summary.parent.mkdir(parents=True, exist_ok=True)

    started_wall = utc_now()
    started = time.monotonic()
    initial = snapshot(tracked, started)
    emit_heartbeat(args.stage, initial)

    process = subprocess.Popen(command)
    stop = threading.Event()
    samples = [initial]

    def heartbeat_loop() -> None:
        while not stop.wait(args.interval_seconds):
            value = snapshot(tracked, started)
            samples.append(value)
            emit_heartbeat(args.stage, value)

    thread = threading.Thread(target=heartbeat_loop, name="needle3-stage-heartbeat", daemon=True)
    thread.start()

    forwarded_signal: int | None = None
    previous_handlers: dict[int, Any] = {}

    def forward(signum: int, _frame: Any) -> None:
        nonlocal forwarded_signal
        forwarded_signal = signum
        if process.poll() is None:
            process.send_signal(signum)

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, forward)

    try:
        return_code = process.wait()
    finally:
        stop.set()
        thread.join(timeout=max(1.0, args.interval_seconds + 1.0))
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)

    final = snapshot(tracked, started)
    samples.append(final)
    emit_heartbeat(args.stage, final)

    if return_code < 0:
        command_signal = -return_code
        shell_exit_code = 128 + command_signal
    else:
        command_signal = forwarded_signal
        shell_exit_code = return_code

    summary = {
        "schema_version": SCHEMA,
        "stage": args.stage,
        "started_at": started_wall,
        "ended_at": utc_now(),
        "elapsed_seconds": final["elapsed_seconds"],
        "command": command,
        "exit_code": int(shell_exit_code),
        "signal": command_signal,
        "child_max_rss_kib": _max_child_rss_kib(),
        "initial": initial,
        "final": final,
        "sample_count": len(samples),
        "min_mem_available_kib": min(
            value["mem_available_kib"]
            for value in samples
            if value["mem_available_kib"] is not None
        )
        if any(value["mem_available_kib"] is not None for value in samples)
        else None,
        "min_root_free_kib": min(value["root_free_kib"] for value in samples),
        "workflow": {
            "repository_head": os.environ.get("GITHUB_SHA"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "runner_os": os.environ.get("RUNNER_OS"),
            "runner_arch": os.environ.get("RUNNER_ARCH"),
            "image_os": os.environ.get("ImageOS"),
            "image_version": os.environ.get("ImageVersion"),
        },
    }
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        "NEEDLE3_STAGE_SUMMARY=PASS "
        f"STAGE={args.stage} EXIT_CODE={shell_exit_code} "
        f"ELAPSED_SECONDS={final['elapsed_seconds']} "
        f"CHILD_MAX_RSS_KIB={summary['child_max_rss_kib']}",
        flush=True,
    )
    return int(shell_exit_code)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run one Needle 3 canary stage with bounded resource heartbeats.")
    p.add_argument("--stage", required=True)
    p.add_argument("--summary", type=pathlib.Path, required=True)
    p.add_argument("--interval-seconds", type=float, default=60.0)
    p.add_argument("--track", action="append", default=[])
    p.add_argument("command", nargs=argparse.REMAINDER)
    return p


def main() -> int:
    return run(parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
