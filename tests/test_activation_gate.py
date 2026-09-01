import json
import unittest
from pathlib import Path

from needle_watch.receipt import build_receipt, is_valid_null, validate_receipt


class ActivationGateTests(unittest.TestCase):
    def _receipt_from_fixture(self, name):
        root = Path(__file__).resolve().parent / "fixtures"
        payload = json.loads((root / name).read_text(encoding="utf-8"))
        return build_receipt(
            run_id=f"fixture-{name}",
            generated_at="2026-09-01T12:00:00Z",
            window_start="2026-08-31T12:00:00Z",
            window_end="2026-09-01T12:00:00Z",
            collector_revision="e" * 40,
            source_health=payload["source_health"],
            candidates=payload["candidates"],
            prior_ids=set(),
        )

    def test_null_day_fixture_is_valid_null(self):
        receipt = self._receipt_from_fixture("null-day-source.json")
        self.assertEqual(validate_receipt(receipt), [])
        self.assertTrue(is_valid_null(receipt))

    def test_source_failure_fixture_is_valid_receipt_but_not_null_day(self):
        receipt = self._receipt_from_fixture("source-failure.json")
        self.assertEqual(validate_receipt(receipt), [])
        self.assertFalse(is_valid_null(receipt))
        self.assertEqual(receipt["source_health"][0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
