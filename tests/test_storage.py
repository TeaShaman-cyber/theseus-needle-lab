import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from needle_watch.storage import load_prior_candidate_ids, write_receipt_snapshot


class StorageTests(unittest.TestCase):
    def test_missing_prior_snapshot_returns_empty_set(self):
        with TemporaryDirectory() as tmp:
            ids = load_prior_candidate_ids(Path(tmp) / "missing.json")
            self.assertEqual(ids, set())

    def test_prior_snapshot_loads_only_candidate_ids(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "prior.json"
            path.write_text(json.dumps({"candidates": [
                {"candidate_id": "a" * 64},
                {"candidate_id": "b" * 64},
                {"title": "missing-id"},
            ]}))
            self.assertEqual(load_prior_candidate_ids(path), {"a" * 64, "b" * 64})

    def test_write_snapshot_makes_dated_and_latest_bytes_identical_and_stable(self):
        receipt = {
            "schema_version": "needle-watch-receipt-v0.1",
            "run_id": "run-1",
            "generated_at": "2026-09-01T10:00:01Z",
            "window_start": "2026-08-31T10:00:00Z",
            "window_end": "2026-09-01T10:00:00Z",
            "collector_revision": "a" * 40,
            "source_health": [{
                "source_id": "github-search:tiny-model",
                "status": "ok",
                "checked_at": "2026-09-01T10:00:00Z",
                "records_seen": 0,
                "cursor_or_watermark": "2026-08-31",
                "error_class": None,
            }],
            "candidates": [],
        }
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            dated, latest = write_receipt_snapshot(
                receipt, repo_root=root, date_key="2026-09-01"
            )
            dated_bytes = dated.read_bytes()
            latest_bytes = latest.read_bytes()
            self.assertEqual(dated_bytes, latest_bytes)
            self.assertTrue(dated_bytes.endswith(b"\n"))
            self.assertEqual(json.loads(dated_bytes), receipt)
            write_receipt_snapshot(receipt, repo_root=root, date_key="2026-09-01")
            self.assertEqual(dated_bytes, dated.read_bytes())


if __name__ == "__main__":
    unittest.main()
