import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from needle_watch.receipt import build_receipt
from needle_watch.storage import write_receipt_snapshot


def valid_receipt() -> dict:
    return build_receipt(
        run_id="run-cli",
        generated_at="2026-09-01T15:00:00Z",
        window_start="2026-08-31T15:00:00Z",
        window_end="2026-09-01T15:00:00Z",
        collector_revision="a" * 40,
        prior_schema_version="needle-watch-receipt-v0.2",
        source_health=[{
            "source_id": "fixture:healthy", "status": "ok",
            "checked_at": "2026-09-01T15:00:00Z", "records_seen": 0,
            "total_count": 0, "returned_count": 0,
            "incomplete_results": False, "truncated": False,
            "cursor_or_watermark": "2026-08-31T15:00:00Z", "error_class": None,
        }],
        candidates=[], prior_ids=set(), prior_entity_ids=set(),
    )


class HandoffCliTests(unittest.TestCase):
    def test_export_cli_writes_single_line_public_outputs(self):
        project_root = Path(__file__).resolve().parents[1]
        script = project_root / "scripts" / "export-needle-watch-output.py"
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            output = Path(tmp) / "github-output.txt"
            write_receipt_snapshot(valid_receipt(), repo_root=root, date_key="2026-09-01")
            env = os.environ.copy()
            env["GITHUB_OUTPUT"] = str(output)
            result = subprocess.run(
                [sys.executable, str(script), "--repo-root", str(root)],
                cwd=project_root, env=env, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            values = dict(line.split("=", 1) for line in output.read_text().splitlines())
            payload = values["receipt_json"]
            self.assertEqual(json.loads(payload), valid_receipt())
            self.assertEqual(
                values["receipt_sha256"],
                hashlib.sha256(payload.encode()).hexdigest(),
            )
            self.assertEqual(int(values["receipt_bytes"]), len(payload.encode()))

    def test_import_cli_recreates_receipt_from_job_output_environment(self):
        project_root = Path(__file__).resolve().parents[1]
        script = project_root / "scripts" / "import-needle-watch-output.py"
        receipt = valid_receipt()
        payload = json.dumps(receipt, separators=(",", ":"), sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            env = os.environ.copy()
            env.update({
                "NEEDLE_WATCH_RECEIPT_JSON": payload,
                "NEEDLE_WATCH_RECEIPT_SHA256": digest,
            })
            result = subprocess.run(
                [sys.executable, str(script), "--repo-root", str(root)],
                cwd=project_root, env=env, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            latest = root / "data" / "latest" / "needle-watch.json"
            run = root / "data" / "runs" / "run-cli.json"
            self.assertTrue(latest.exists())
            self.assertEqual(latest.read_bytes(), run.read_bytes())
            self.assertEqual(json.loads(latest.read_text()), receipt)


if __name__ == "__main__":
    unittest.main()
