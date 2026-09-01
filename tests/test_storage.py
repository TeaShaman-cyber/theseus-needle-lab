import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from needle_watch.storage import (
    load_prior_candidate_ids,
    load_prior_entity_ids,
    write_receipt_snapshot,
)


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

    def test_prior_snapshot_loads_stable_source_entity_ids(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "prior.json"
            path.write_text(json.dumps({"candidates": [
                {"source_entity_id": "github-repo:1"},
                {"source_entity_id": "github-repo:2"},
                {"candidate_id": "missing-entity"},
            ]}))
            self.assertEqual(
                load_prior_entity_ids(path),
                {"github-repo:1", "github-repo:2"},
            )

    def test_write_snapshot_preserves_each_run_when_same_day_is_repeated(self):
        first = {
            "schema_version": "needle-watch-receipt-v0.1",
            "run_id": "run-1",
            "generated_at": "2026-09-01T10:00:01Z",
            "window_start": "2026-08-31T10:00:00Z",
            "window_end": "2026-09-01T10:00:00Z",
            "collector_revision": "a" * 40,
            "source_health": [{
                "source_id": "fixture", "status": "ok",
                "checked_at": "2026-09-01T10:00:00Z",
                "records_seen": 0, "cursor_or_watermark": None,
                "error_class": None,
            }],
            "candidates": [],
        }
        second = dict(first, run_id="run-2", generated_at="2026-09-01T11:00:01Z")
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run1, daily1, latest1 = write_receipt_snapshot(
                first, repo_root=root, date_key="2026-09-01"
            )
            run1_bytes = run1.read_bytes()
            run2, daily2, latest2 = write_receipt_snapshot(
                second, repo_root=root, date_key="2026-09-01"
            )
            self.assertNotEqual(run1, run2)
            self.assertEqual(run1, root / "data" / "runs" / "run-1.json")
            self.assertEqual(run2, root / "data" / "runs" / "run-2.json")
            self.assertEqual(run1.read_bytes(), run1_bytes)
            self.assertEqual(json.loads(run2.read_text()), second)
            self.assertEqual(daily1, daily2)
            self.assertEqual(daily2, root / "data" / "daily" / "2026-09-01.json")
            self.assertEqual(daily2.read_bytes(), latest2.read_bytes())
            self.assertEqual(json.loads(latest2.read_text())["run_id"], "run-2")

    def test_write_snapshot_makes_run_daily_and_latest_bytes_identical_and_stable(self):
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
            run, daily, latest = write_receipt_snapshot(
                receipt, repo_root=root, date_key="2026-09-01"
            )
            run_bytes = run.read_bytes()
            self.assertEqual(run_bytes, daily.read_bytes())
            self.assertEqual(run_bytes, latest.read_bytes())
            self.assertTrue(run_bytes.endswith(b"\n"))
            self.assertEqual(json.loads(run_bytes), receipt)
            write_receipt_snapshot(receipt, repo_root=root, date_key="2026-09-01")
            self.assertEqual(run_bytes, run.read_bytes())


if __name__ == "__main__":
    unittest.main()
