import unittest

from needle_watch.receipt import (
    SCHEMA_VERSION,
    build_receipt,
    is_valid_null,
    stable_candidate_id,
    validate_receipt,
)


class ReceiptContractTests(unittest.TestCase):
    def test_schema_version_marks_v02_contract(self):
        self.assertEqual(SCHEMA_VERSION, "needle-watch-receipt-v0.2")

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

    def test_build_receipt_marks_exact_observation_seen_in_previous_snapshot(self):
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
        self.assertTrue(receipt["candidates"][0]["seen_in_previous_snapshot"])
        self.assertFalse(receipt["candidates"][0]["entity_seen_in_previous_snapshot"])
        self.assertEqual(prior_id, receipt["candidates"][0]["candidate_id"])

    def test_build_receipt_preserves_entity_and_immutable_revision_identity(self):
        candidate = {
            "source_id": "github-search:tiny-model",
            "source_class": "github_repo",
            "source_entity_id": "github-repo:123456",
            "canonical_url": "https://github.com/example/project",
            "title": "Example Project",
            "observed_at": "2026-09-01T10:00:00Z",
            "published_or_pushed_at": "2026-09-01T09:00:00Z",
            "source_identity": "example/project@main",
            "upstream_revision": "e" * 40,
            "discovery_route": "github_search:tiny-model",
            "matched_watch_lines": ["tiny-model"],
            "content_fingerprint": "commit:" + "e" * 40,
        }
        receipt = build_receipt(
            run_id="run-identity",
            generated_at="2026-09-01T10:00:01Z",
            window_start="2026-08-31T10:00:00Z",
            window_end="2026-09-01T10:00:00Z",
            collector_revision="a" * 40,
            source_health=[{
                "source_id": "github-search:tiny-model",
                "status": "ok",
                "checked_at": "2026-09-01T10:00:00Z",
                "records_seen": 1,
                "cursor_or_watermark": "2026-08-31T10:00:00Z",
                "error_class": None,
            }],
            candidates=[candidate],
            prior_ids=set(),
        )
        normalized = receipt["candidates"][0]
        self.assertEqual(normalized["source_entity_id"], "github-repo:123456")
        self.assertEqual(normalized["upstream_revision"], "e" * 40)

    def test_build_receipt_separates_exact_observation_from_same_entity_seen(self):
        candidate = {
            "source_id": "github-search:tiny-model",
            "source_class": "github_repo",
            "source_entity_id": "github-repo:123456",
            "canonical_url": "https://github.com/example/project",
            "title": "Example Project",
            "observed_at": "2026-09-01T10:00:00Z",
            "published_or_pushed_at": "2026-09-01T09:00:00Z",
            "source_identity": "example/project@main",
            "upstream_revision": "f" * 40,
            "discovery_route": "github_search:tiny-model",
            "matched_watch_lines": ["tiny-model"],
            "content_fingerprint": "commit:" + "f" * 40,
        }
        receipt = build_receipt(
            run_id="run-seen",
            generated_at="2026-09-01T10:00:01Z",
            window_start="2026-08-31T10:00:00Z",
            window_end="2026-09-01T10:00:00Z",
            collector_revision="a" * 40,
            source_health=[{
                "source_id": "github-search:tiny-model",
                "status": "ok",
                "checked_at": "2026-09-01T10:00:00Z",
                "records_seen": 1,
                "cursor_or_watermark": "2026-08-31T10:00:00Z",
                "error_class": None,
            }],
            candidates=[candidate],
            prior_ids={"0" * 64},
            prior_entity_ids={"github-repo:123456"},
        )
        normalized = receipt["candidates"][0]
        self.assertFalse(normalized["seen_in_previous_snapshot"])
        self.assertTrue(normalized["entity_seen_in_previous_snapshot"])
        self.assertNotIn("prior_seen", normalized)

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
                "total_count": 0,
                "returned_count": 0,
                "incomplete_results": False,
                "truncated": False,
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
            "total_count": None,
            "returned_count": 0,
            "incomplete_results": None,
            "truncated": None,
            "cursor_or_watermark": None,
            "error_class": "HTTPError",
        }]
        self.assertTrue(is_valid_null(healthy))
        self.assertFalse(is_valid_null(failed))

    def test_validate_receipt_rejects_ok_status_with_incomplete_coverage(self):
        receipt = build_receipt(
            run_id="run-health-state",
            generated_at="2026-09-01T10:00:01Z",
            window_start="2026-08-31T10:00:00Z",
            window_end="2026-09-01T10:00:00Z",
            collector_revision="c" * 40,
            source_health=[{
                "source_id": "github-search:tiny-model", "status": "ok",
                "checked_at": "2026-09-01T10:00:00Z", "records_seen": 10,
                "total_count": 14, "returned_count": 10,
                "incomplete_results": False, "truncated": True,
                "cursor_or_watermark": "2026-08-31T10:00:00Z",
                "error_class": None,
            }],
            candidates=[], prior_ids=set(),
        )
        errors = validate_receipt(receipt)
        self.assertTrue(any("status ok requires complete coverage" in error for error in errors), errors)

    def test_validate_receipt_rejects_non_increasing_window(self):
        receipt = build_receipt(
            run_id="run-window",
            generated_at="2026-09-01T10:00:01Z",
            window_start="2026-09-01T10:00:00Z",
            window_end="2026-09-01T09:00:00Z",
            collector_revision="c" * 40,
            source_health=[{
                "source_id": "github-search:tiny-model", "status": "ok",
                "checked_at": "2026-09-01T10:00:00Z", "records_seen": 0,
                "total_count": 0, "returned_count": 0,
                "incomplete_results": False, "truncated": False,
                "cursor_or_watermark": "2026-09-01T10:00:00Z",
                "error_class": None,
            }],
            candidates=[], prior_ids=set(),
        )
        errors = validate_receipt(receipt)
        self.assertTrue(any("window_start must be before window_end" in error for error in errors), errors)

    def test_validate_receipt_rejects_candidate_id_that_does_not_match_identity(self):
        candidate = {
            "source_id": "github-search:tiny-model",
            "source_class": "github_repo",
            "source_entity_id": "github-repo:123456",
            "canonical_url": "https://github.com/example/project",
            "title": "Example Project",
            "observed_at": "2026-09-01T10:00:00Z",
            "published_or_pushed_at": "2026-09-01T09:00:00Z",
            "source_identity": "example/project@main",
            "upstream_revision": "e" * 40,
            "discovery_route": "github_search:tiny-model",
            "matched_watch_lines": ["tiny-model"],
            "content_fingerprint": "commit:" + "e" * 40,
        }
        receipt = build_receipt(
            run_id="run-id-check",
            generated_at="2026-09-01T10:00:01Z",
            window_start="2026-08-31T10:00:00Z",
            window_end="2026-09-01T10:00:00Z",
            collector_revision="c" * 40,
            source_health=[{
                "source_id": "github-search:tiny-model", "status": "ok",
                "checked_at": "2026-09-01T10:00:00Z", "records_seen": 1,
                "total_count": 1, "returned_count": 1,
                "incomplete_results": False, "truncated": False,
                "cursor_or_watermark": "2026-08-31T10:00:00Z",
                "error_class": None,
            }],
            candidates=[candidate], prior_ids=set(),
        )
        receipt["candidates"][0]["candidate_id"] = "0" * 64
        errors = validate_receipt(receipt)
        self.assertTrue(any("candidate_id mismatch" in error for error in errors), errors)

    def test_validate_receipt_rejects_source_health_without_coverage_evidence(self):
        receipt = build_receipt(
            run_id="run-health",
            generated_at="2026-09-01T10:00:01Z",
            window_start="2026-08-31T10:00:00Z",
            window_end="2026-09-01T10:00:00Z",
            collector_revision="c" * 40,
            source_health=[{
                "source_id": "github-search:tiny-model",
                "status": "ok",
                "checked_at": "2026-09-01T10:00:00Z",
                "records_seen": 1,
                "cursor_or_watermark": "2026-08-31T10:00:00Z",
                "error_class": None,
            }],
            candidates=[],
            prior_ids=set(),
        )
        errors = validate_receipt(receipt)
        self.assertTrue(any("total_count" in error for error in errors), errors)
        self.assertTrue(any("incomplete_results" in error for error in errors), errors)
        self.assertTrue(any("truncated" in error for error in errors), errors)

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
