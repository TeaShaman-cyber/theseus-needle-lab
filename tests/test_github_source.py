import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from needle_watch.github_source import (
    build_search_url,
    collect_github_queries,
    load_watch_config,
    parse_repository_item,
)


REPO_ITEM = {
    "full_name": "example/tiny-agent",
    "html_url": "https://github.com/example/tiny-agent",
    "name": "tiny-agent",
    "description": "A tiny language-model helper",
    "default_branch": "main",
    "pushed_at": "2026-09-01T09:15:00Z",
    "updated_at": "2026-09-01T09:20:00Z",
}


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class GithubSourceTests(unittest.TestCase):
    def test_load_watch_config_reads_versioned_query_config(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "watch.json"
            path.write_text(json.dumps({"github": {"queries": [{"id": "tiny"}]}}))
            self.assertEqual(load_watch_config(path)["github"]["queries"][0]["id"], "tiny")

    def test_build_search_url_encodes_query_and_page_bound(self):
        url = build_search_url("tiny language model pushed:>=2026-08-31", 7)
        self.assertIn("api.github.com/search/repositories", url)
        self.assertIn("per_page=7", url)
        self.assertIn("sort=updated", url)
        self.assertIn("order=desc", url)
        self.assertIn("tiny+language+model", url)

    def test_parse_repository_item_preserves_re_fetch_identity(self):
        candidate = parse_repository_item(
            REPO_ITEM,
            source_id="github-search:tiny-model",
            discovery_route="github_search:tiny-model",
            matched_watch_lines=["tiny-model"],
            observed_at="2026-09-01T10:00:00Z",
        )
        self.assertEqual(candidate["canonical_url"], REPO_ITEM["html_url"])
        self.assertEqual(candidate["source_identity"], "example/tiny-agent@main")
        self.assertEqual(candidate["content_fingerprint"], "pushed:2026-09-01T09:15:00Z")
        self.assertEqual(candidate["matched_watch_lines"], ["tiny-model"])

    def test_collect_github_queries_returns_candidates_and_healthy_source_record(self):
        config = {
            "github": {
                "queries": [{
                    "id": "tiny-model",
                    "query": "tiny language model",
                    "watch_lines": ["tiny-model"],
                    "per_page": 5,
                }]
            }
        }
        seen_requests = []

        def opener(request, timeout=0):
            seen_requests.append(request)
            return FakeResponse({"items": [REPO_ITEM]})

        candidates, health = collect_github_queries(
            config,
            token="test-token",
            observed_at="2026-09-01T10:00:00Z",
            since_date="2026-08-31",
            opener=opener,
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(health[0]["status"], "ok")
        self.assertEqual(health[0]["records_seen"], 1)
        self.assertEqual(health[0]["cursor_or_watermark"], "2026-08-31")
        self.assertIn("pushed%3A%3E%3D2026-08-31", seen_requests[0].full_url)
        self.assertEqual(seen_requests[0].get_header("Authorization"), "Bearer test-token")

    def test_collect_github_queries_marks_partial_when_one_item_is_malformed(self):
        config = {
            "github": {
                "queries": [{
                    "id": "tiny-model",
                    "query": "tiny language model",
                    "watch_lines": ["tiny-model"],
                    "per_page": 5,
                }]
            }
        }

        def opener(request, timeout=0):
            return FakeResponse({"items": [REPO_ITEM, {"name": "broken"}]})

        candidates, health = collect_github_queries(
            config,
            token=None,
            observed_at="2026-09-01T10:00:00Z",
            since_date="2026-08-31",
            opener=opener,
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(health[0]["status"], "partial")
        self.assertEqual(health[0]["records_seen"], 2)
        self.assertEqual(health[0]["error_class"], "MalformedItem")

    def test_collect_github_queries_marks_failed_source_without_candidates(self):
        config = {
            "github": {
                "queries": [{
                    "id": "tiny-model",
                    "query": "tiny language model",
                    "watch_lines": ["tiny-model"],
                }]
            }
        }

        def opener(request, timeout=0):
            raise OSError("network down")

        candidates, health = collect_github_queries(
            config,
            token=None,
            observed_at="2026-09-01T10:00:00Z",
            since_date="2026-08-31",
            opener=opener,
        )
        self.assertEqual(candidates, [])
        self.assertEqual(health[0]["status"], "failed")
        self.assertEqual(health[0]["error_class"], "OSError")


if __name__ == "__main__":
    unittest.main()
