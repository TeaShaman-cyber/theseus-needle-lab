import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from needle_watch.handoff import (
    MAX_HANDOFF_BYTES,
    export_receipt_handoff,
    import_receipt_handoff,
)
from needle_watch.receipt import build_receipt
from needle_watch.storage import write_receipt_snapshot


def valid_receipt(run_id: str = "run-handoff") -> dict:
    return build_receipt(
        run_id=run_id,
        generated_at="2026-09-01T15:00:00Z",
        window_start="2026-08-31T15:00:00Z",
        window_end="2026-09-01T15:00:00Z",
        collector_revision="a" * 40,
        prior_schema_version="needle-watch-receipt-v0.2",
        source_health=[{
            "source_id": "fixture:healthy",
            "status": "ok",
            "checked_at": "2026-09-01T15:00:00Z",
            "records_seen": 0,
            "total_count": 0,
            "returned_count": 0,
            "incomplete_results": False,
            "truncated": False,
            "cursor_or_watermark": "2026-08-31T15:00:00Z",
            "error_class": None,
        }],
        candidates=[],
        prior_ids=set(),
        prior_entity_ids=set(),
    )


class HandoffTests(unittest.TestCase):
    def test_export_returns_compact_validated_json_and_sha256(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = valid_receipt()
            write_receipt_snapshot(receipt, repo_root=root, date_key="2026-09-01")

            payload, digest = export_receipt_handoff(root)

            self.assertNotIn("\n", payload)
            self.assertEqual(json.loads(payload), receipt)
            self.assertEqual(
                digest,
                hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            )
            self.assertLess(len(payload.encode("utf-8")), MAX_HANDOFF_BYTES)

    def test_export_rejects_when_snapshot_views_do_not_match(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = valid_receipt()
            run, daily, latest = write_receipt_snapshot(
                receipt, repo_root=root, date_key="2026-09-01"
            )
            daily.write_text('{"corrupt":true}\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "snapshot bytes differ"):
                export_receipt_handoff(root)

    def test_import_rejects_digest_mismatch(self):
        receipt = valid_receipt()
        payload = json.dumps(receipt, separators=(",", ":"), sort_keys=True)
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                import_receipt_handoff(Path(tmp), payload, "0" * 64)

    def test_import_rejects_oversized_payload_before_json_parse(self):
        oversized = "x" * (MAX_HANDOFF_BYTES + 1)
        digest = hashlib.sha256(oversized.encode("utf-8")).hexdigest()
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "exceeds size limit"):
                import_receipt_handoff(Path(tmp), oversized, digest)

    def test_import_revalidates_and_recreates_canonical_snapshot_files(self):
        receipt = valid_receipt("run-roundtrip")
        payload = json.dumps(
            receipt,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=False,
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run, daily, latest = import_receipt_handoff(root, payload, digest)
            self.assertEqual(run.name, "run-roundtrip.json")
            self.assertEqual(daily.name, "2026-09-01.json")
            self.assertEqual(run.read_bytes(), daily.read_bytes())
            self.assertEqual(run.read_bytes(), latest.read_bytes())
            self.assertEqual(json.loads(latest.read_text()), receipt)


if __name__ == "__main__":
    unittest.main()
