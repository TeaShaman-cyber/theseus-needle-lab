import unittest

from needle_watch.receipt import (
    build_receipt,
    is_valid_null,
    stable_candidate_id,
    validate_receipt,
)


class ReceiptContractTests(unittest.TestCase):
    def test_candidate_id_is_deterministic_and_content_sensitive(self):
        base = stable_candidate_id(
            "github_repo",
            "https://github.com/example/project",
            "example/project@main",
            "pushed:2026-09-01T00:00:00Z",
        )
        same = stable_candidate_id(
            "github_repo",
            "https://github.com/example/project",
            "example/project@main",
            "pushed:2026-09-01T00:00:00Z",
        )
        changed = stable_candidate_id(
            "github_repo",
            "https://github.com/example/project",
            "example/project@main",
            "pushed:2026-09-02T00:00:00Z",
        )
        self.assertEqual(base, same)
        self.assertNotEqual(base, changed)
        self.assertRegex(base, r"^[0-9a-f]{64}$")

    def test_build_receipt_marks_prior_seen_from_stable_candidate_id(self):
        candidate = {
            "source_id": "github-search:tiny-model",
            "source_class": "github_repo",
            "canonical_url": "https://github.com/example/project",
            "title": "Example Project",
            "observed_at": "2026-09-01T10:00:00Z",
            "published_or_pushed_at": "2026-09-01T09:00:00Z",
            "source_identity": "example/project@main",
            "discovery_route": "github_search:tiny-model",
            "matched_watch_lines": ["tiny-model"],
            "content_fingerprint": "pushed:2026-09-01T09:00:00Z",
        }
        prior_id = stable_candidate_id(
            candidate["source_class"],
            candidate["canonical_url"],
            candidate["source_identity"],
            candidate["content_fingerprint"],
        )
        receipt = build_receipt(
            run_id="run-1",
            generated_at="2026-09-01T10:00:01Z",
            window_start="2026-08-31T10:00:00Z",
            window_end="2026-09-01T10:00:00Z",
            collector_revision="a" * 40,
            source_health=[{
                "source_id": "github-search:tiny-model",
                "status": "ok",
                "checked_at": "2026-09-01T10:00:00Z",
                "records_seen": 1,
                "cursor_or_watermark": None,
                "error_class": None,
            }],
            candidates=[candidate],
            prior_ids={prior_id},
        )
        self.assertTrue(receipt["candidates"][0]["prior_seen"])
        self.assertEqual(prior_id, receipt["candidates"][0]["candidate_id"])

    def test_valid_null_requires_healthy_source_evidence(self):
        healthy = build_receipt(
            run_id="run-null",
            generated_at="2026-09-01T10:00:01Z",
            window_start="2026-08-31T10:00:00Z",
            window_end="2026-09-01T10:00:00Z",
            collector_revision="b" * 40,
            source_health=[{
                "source_id": "github-search:tiny-model",
                "status": "ok",
                "checked_at": "2026-09-01T10:00:00Z",
                "records_seen": 0,
                "cursor_or_watermark": None,
                "error_class": None,
            }],
            candidates=[],
            prior_ids=set(),
        )
        failed = dict(healthy)
        failed["source_health"] = [{
            "source_id": "github-search:tiny-model",
            "status": "failed",
            "checked_at": "2026-09-01T10:00:00Z",
            "records_seen": 0,
            "cursor_or_watermark": None,
            "error_class": "HTTPError",
        }]
        self.assertTrue(is_valid_null(healthy))
        self.assertFalse(is_valid_null(failed))

    def test_validate_receipt_rejects_missing_source_health(self):
        receipt = {
            "schema_version": "needle-watch-receipt-v0.1",
            "run_id": "run-1",
            "generated_at": "2026-09-01T10:00:01Z",
            "window_start": "2026-08-31T10:00:00Z",
            "window_end": "2026-09-01T10:00:00Z",
            "collector_revision": "c" * 40,
            "source_health": [],
            "candidates": [],
        }
        errors = validate_receipt(receipt)
        self.assertIn("source_health must contain at least one record", errors)


if __name__ == "__main__":
    unittest.main()
