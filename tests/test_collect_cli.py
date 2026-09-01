import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class CollectCliTests(unittest.TestCase):
    def test_fixture_mode_writes_valid_dated_and_latest_receipts(self):
        project_root = Path(__file__).resolve().parents[1]
        script = project_root / "scripts" / "collect-needle-watch.py"
        config = project_root / "config" / "needle-watch.json"
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            fixture = repo_root / "fixture.json"
            fixture.write_text(json.dumps({
                "source_health": [{
                    "source_id": "fixture:healthy",
                    "status": "ok",
                    "checked_at": "2026-09-01T12:00:00Z",
                    "records_seen": 0,
                    "cursor_or_watermark": "2026-08-31",
                    "error_class": None,
                }],
                "candidates": [],
            }))
            env = os.environ.copy()
            env.update({
                "NEEDLE_WATCH_NOW": "2026-09-01T12:00:00Z",
                "NEEDLE_WATCH_RUN_ID": "fixture-run-1",
                "NEEDLE_WATCH_COLLECTOR_REVISION": "d" * 40,
                "PYTHONDONTWRITEBYTECODE": "1",
            })
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--repo-root",
                    str(repo_root),
                    "--config",
                    str(config),
                    "--fixture-source",
                    str(fixture),
                ],
                cwd=project_root,
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("NEEDLE_WATCH_RECEIPT PASS", result.stdout)
            dated = repo_root / "data" / "2026-09-01" / "needle-watch.json"
            latest = repo_root / "data" / "latest" / "needle-watch.json"
            self.assertEqual(dated.read_bytes(), latest.read_bytes())
            receipt = json.loads(latest.read_text())
            self.assertEqual(receipt["run_id"], "fixture-run-1")
            self.assertEqual(receipt["collector_revision"], "d" * 40)
            self.assertEqual(receipt["candidates"], [])


if __name__ == "__main__":
    unittest.main()
