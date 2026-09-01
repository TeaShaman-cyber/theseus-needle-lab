from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _remote_tracking_ref(target_ref: str, remote: str) -> str:
    if not target_ref or "\n" in target_ref or "\r" in target_ref or target_ref.startswith("-"):
        raise ValueError("target_ref must be a safe branch name")
    return f"refs/remotes/{remote}/{target_ref}"


def _fetch_target(repo_root: Path, target_ref: str, remote: str) -> str:
    tracking = _remote_tracking_ref(target_ref, remote)
    _git(repo_root, "fetch", remote, f"{target_ref}:{tracking}")
    return tracking


def restore_remote_latest(
    repo_root: Path,
    *,
    target_ref: str,
    remote: str = "origin",
) -> bool:
    """Restore only the latest receipt state without changing checked-out code."""
    tracking = _fetch_target(repo_root, target_ref, remote)
    result = _git(
        repo_root,
        "show",
        f"{tracking}:data/latest/needle-watch.json",
        check=False,
    )
    if result.returncode != 0:
        return False
    latest = repo_root / "data" / "latest" / "needle-watch.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_bytes(result.stdout)
    return True


def _generated_receipt_paths(repo_root: Path) -> list[Path]:
    latest = repo_root / "data" / "latest" / "needle-watch.json"
    receipt = json.loads(latest.read_text(encoding="utf-8"))
    run_id = receipt["run_id"]
    generated_at = receipt["generated_at"]
    if not isinstance(run_id, str) or Path(run_id).name != run_id:
        raise ValueError("receipt run_id is not path-safe")
    if not isinstance(generated_at, str) or len(generated_at) < 10:
        raise ValueError("receipt generated_at is invalid")
    date_key = generated_at[:10]
    return [
        repo_root / "data" / "runs" / f"{run_id}.json",
        repo_root / "data" / "daily" / f"{date_key}.json",
        latest,
    ]


def publish_generated_receipt(
    repo_root: Path,
    *,
    target_ref: str,
    remote: str = "origin",
) -> str | None:
    """Publish generated receipt bytes on top of the current remote branch tip."""
    paths = _generated_receipt_paths(repo_root)
    payloads = {path.relative_to(repo_root): path.read_bytes() for path in paths}
    if len(set(payloads.values())) != 1:
        raise ValueError("generated run, daily, and latest receipt bytes differ")

    tracking = _fetch_target(repo_root, target_ref, remote)
    _git(repo_root, "reset", "--hard", tracking)

    for relative, data in payloads.items():
        path = repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    relative_names = [str(path) for path in payloads]
    _git(repo_root, "add", "--", *relative_names)
    staged = _git(repo_root, "diff", "--cached", "--quiet", check=False)
    if staged.returncode == 0:
        return None
    if staged.returncode != 1:
        raise subprocess.CalledProcessError(
            staged.returncode, ["git", "diff", "--cached", "--quiet"]
        )

    _git(repo_root, "commit", "-m", "Collect Needle Watch discovery receipt")
    _git(repo_root, "push", remote, f"HEAD:{target_ref}")
    return _git(repo_root, "rev-parse", "HEAD").stdout.decode().strip()
