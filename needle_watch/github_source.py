from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

GITHUB_SEARCH_ENDPOINT = "https://api.github.com/search/repositories"


def load_watch_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_search_url(query: str, per_page: int) -> str:
    params = urlencode(
        {
            "q": query,
            "per_page": per_page,
            "sort": "updated",
            "order": "desc",
        }
    )
    return f"{GITHUB_SEARCH_ENDPOINT}?{params}"


def parse_repository_item(
    item: dict,
    *,
    source_id: str,
    discovery_route: str,
    matched_watch_lines: list[str],
    observed_at: str,
    upstream_revision: str,
) -> dict:
    full_name = item["full_name"]
    default_branch = item["default_branch"]
    pushed_at = item["pushed_at"]
    return {
        "source_id": source_id,
        "source_class": "github_repo",
        "source_entity_id": f"github-repo:{item['id']}",
        "canonical_url": item["html_url"],
        "title": full_name,
        "observed_at": observed_at,
        "published_or_pushed_at": pushed_at,
        "source_identity": f"{full_name}@{default_branch}",
        "upstream_revision": upstream_revision,
        "discovery_route": discovery_route,
        "matched_watch_lines": list(matched_watch_lines),
        "content_fingerprint": f"commit:{upstream_revision}",
    }


def resolve_default_branch_head(
    item: dict,
    *,
    headers: dict[str, str],
    opener=urlopen,
) -> str:
    full_name = item["full_name"]
    default_branch = item["default_branch"]
    url = (
        f"https://api.github.com/repos/{full_name}/commits/"
        f"{quote(default_branch, safe='')}"
    )
    request = Request(url, headers=headers)
    with opener(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    sha = payload["sha"]
    if not isinstance(sha, str) or not sha:
        raise ValueError("default branch commit SHA missing")
    return sha


def collect_github_queries(
    config: dict,
    *,
    token: str | None,
    observed_at: str,
    since_date: str,
    opener=urlopen,
) -> tuple[list[dict], list[dict]]:
    candidates: list[dict] = []
    source_health: list[dict] = []

    for query_config in config.get("github", {}).get("queries", []):
        query_id = query_config["id"]
        source_id = f"github-search:{query_id}"
        discovery_route = f"github_search:{query_id}"
        per_page = int(query_config.get("per_page", 10))
        query = f'{query_config["query"]} pushed:>={since_date}'
        url = build_search_url(query, per_page)
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "theseus-needle-watch/0.2",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(url, headers=headers)

        health = {
            "source_id": source_id,
            "status": "ok",
            "checked_at": observed_at,
            "records_seen": 0,
            "total_count": None,
            "returned_count": 0,
            "incomplete_results": None,
            "truncated": None,
            "cursor_or_watermark": since_date,
            "error_class": None,
        }

        try:
            with opener(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            items = payload.get("items", [])
            total_count = int(payload.get("total_count", len(items)))
            incomplete_results = bool(payload.get("incomplete_results", False))
            health["records_seen"] = len(items)
            health["total_count"] = total_count
            health["returned_count"] = len(items)
            health["incomplete_results"] = incomplete_results
            health["truncated"] = total_count > len(items)
            if incomplete_results:
                health["status"] = "partial"
                health["error_class"] = "IncompleteResults"
            elif health["truncated"]:
                health["status"] = "partial"
                health["error_class"] = "ResultTruncated"
            malformed = False
            revision_failed = False
            for item in items:
                try:
                    item["id"]
                    item["full_name"]
                    item["html_url"]
                    item["default_branch"]
                    item["pushed_at"]
                except (KeyError, TypeError):
                    malformed = True
                    continue
                try:
                    upstream_revision = resolve_default_branch_head(
                        item, headers=headers, opener=opener
                    )
                except (OSError, ValueError, KeyError, TypeError):
                    revision_failed = True
                    continue
                try:
                    candidates.append(
                        parse_repository_item(
                            item,
                            source_id=source_id,
                            discovery_route=discovery_route,
                            matched_watch_lines=query_config.get("watch_lines", []),
                            observed_at=observed_at,
                            upstream_revision=upstream_revision,
                        )
                    )
                except (KeyError, TypeError):
                    malformed = True
            if revision_failed:
                health["status"] = "partial"
                health["error_class"] = "RevisionResolutionFailed"
            elif malformed:
                health["status"] = "partial"
                health["error_class"] = "MalformedItem"
        except (OSError, ValueError) as exc:
            health["status"] = "failed"
            health["error_class"] = type(exc).__name__

        source_health.append(health)

    return candidates, source_health
