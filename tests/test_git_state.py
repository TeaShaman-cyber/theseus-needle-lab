import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from needle_watch.git_state import publish_generated_receipt, restore_remote_latest


def git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def write_receipt(root: Path, run_id: str, generated_at: str, marker: str) -> None:
    receipt = {
        "schema_version": "needle-watch-receipt-v0.2",
        "run_id": run_id,
        "generated_at": generated_at,
        "window_start": "2026-08-31T14:00:00Z",
        "window_end": generated_at,
        "collector_revision": marker * 40,
        "source_health": [],
        "candidates": [],
    }
    data = (json.dumps(receipt, sort_keys=True) + "\n").encode()
    date_key = generated_at[:10]
    paths = [
        root / "data" / "runs" / f"{run_id}.json",
        root / "data" / "daily" / f"{date_key}.json",
        root / "data" / "latest" / "needle-watch.json",
    ]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class GitStateTests(unittest.TestCase):
    def test_restore_then_publish_preserves_prior_bot_commit_on_rerun(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            remote = base / "remote.git"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)

            seed = base / "seed"
            subprocess.run(["git", "clone", str(remote), str(seed)], check=True, capture_output=True)
            git(seed, "config", "user.name", "test")
            git(seed, "config", "user.email", "test@example.com")
            (seed / "keep.txt").write_text("keep\n")
            write_receipt(seed, "seed", "2026-09-01T13:00:00Z", "a")
            git(seed, "add", ".")
            git(seed, "commit", "-m", "seed")
            git(seed, "branch", "-M", "main")
            git(seed, "push", "-u", "origin", "main")
            subprocess.run(["git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
            original_sha = git(seed, "rev-parse", "HEAD")

            runner = base / "runner"
            subprocess.run(["git", "clone", str(remote), str(runner)], check=True, capture_output=True)
            git(runner, "config", "user.name", "github-actions[bot]")
            git(runner, "config", "user.email", "bot@example.com")
            git(runner, "checkout", original_sha)

            write_receipt(seed, "run-attempt-1", "2026-09-01T14:00:00Z", "b")
            git(seed, "add", "data")
            git(seed, "commit", "-m", "attempt 1")
            git(seed, "push", "origin", "main")
            attempt1_sha = git(seed, "rev-parse", "HEAD")

            restored = restore_remote_latest(runner, target_ref="main")
            self.assertTrue(restored)
            self.assertEqual(git(runner, "rev-parse", "HEAD"), original_sha)
            restored_latest = json.loads((runner / "data/latest/needle-watch.json").read_text())
            self.assertEqual(restored_latest["run_id"], "run-attempt-1")

            write_receipt(runner, "run-attempt-2", "2026-09-01T14:10:00Z", "c")
            published_sha = publish_generated_receipt(runner, target_ref="main")
            self.assertTrue(published_sha)

            verify = base / "verify"
            subprocess.run(["git", "clone", str(remote), str(verify)], check=True, capture_output=True)
            self.assertEqual((verify / "keep.txt").read_text(), "keep\n")
            self.assertTrue((verify / "data/runs/run-attempt-1.json").exists())
            self.assertTrue((verify / "data/runs/run-attempt-2.json").exists())
            latest = json.loads((verify / "data/latest/needle-watch.json").read_text())
            self.assertEqual(latest["run_id"], "run-attempt-2")
            self.assertNotEqual(attempt1_sha, published_sha)


if __name__ == "__main__":
    unittest.main()
