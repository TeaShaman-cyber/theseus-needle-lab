# Needle Watch CI Receipts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic public GitHub Actions collector that publishes provenance-bearing Needle Watch discovery receipts consumable by ChatGPT shadow Arms B and C.

**Architecture:** A small Python-stdlib collector reads versioned watch-line query configuration, performs bounded public GitHub repository discovery, records per-query source health, normalizes candidates into receipt schema `needle-watch-receipt-v0.1`, and writes identical dated/latest JSON snapshots. Scientific relevance remains outside CI; the collector only emits candidates and operational provenance.

**Tech Stack:** Python 3.11+ stdlib (`urllib`, `json`, `hashlib`, `datetime`, `unittest`) with GitHub Actions pinned to Python 3.12, GitHub REST API, GitHub Actions.

**Spec:** GitHub Issue #21, especially comments `issuecomment-5492981812` (receipt v0.1) and `issuecomment-5493002007` (Scheduled Tasks / app-routing evidence).

## Global Constraints

- Public sources only; no private repository, user, chat, training, or secret content in receipts.
- CI performs no LLM/AI judgment and no Notion writes.
- `candidate_id` is deterministic from canonical candidate identity.
- Valid null days require explicit healthy source records.
- `data/latest/needle-watch.json` is a convenience pointer; dated snapshots are replay evidence.
- Every write is deterministic JSON with stable key ordering and terminal newline.
- Workflow validates before committing generated receipt files.
- GitHub Actions artifacts may assist diagnostics but are not the canonical history.

---

### Task 1: Receipt normalization and validation

**Files:**
- Create: `needle_watch/__init__.py`
- Create: `needle_watch/receipt.py`
- Create: `tests/test_receipt.py`

**Interfaces:**
- Produces: `stable_candidate_id(source_class: str, canonical_url: str, source_identity: str, content_fingerprint: str) -> str`
- Produces: `normalize_candidate(raw: dict, prior_ids: set[str]) -> dict`
- Produces: `build_receipt(*, run_id: str, generated_at: str, window_start: str, window_end: str, collector_revision: str, source_health: list[dict], candidates: list[dict], prior_ids: set[str]) -> dict`
- Produces: `validate_receipt(receipt: dict) -> list[str]`
- Produces: `is_valid_null(receipt: dict) -> bool`

- [x] **Step 1: Write failing tests for deterministic IDs, prior_seen, valid-null semantics, and required fields.**
- [x] **Step 2: Run `python -m unittest tests.test_receipt -v` and verify RED failures are feature-missing failures.**
- [x] **Step 3: Implement the minimal receipt functions.**
- [x] **Step 4: Re-run receipt tests and verify GREEN.**
- [ ] **Step 5: Commit Task 1.**

### Task 2: GitHub repository discovery adapter

**Files:**
- Create: `needle_watch/github_source.py`
- Create: `tests/test_github_source.py`
- Create: `config/needle-watch.json`

**Interfaces:**
- Consumes: candidate shape accepted by `normalize_candidate`.
- Produces: `load_watch_config(path: Path) -> dict`
- Produces: `build_search_url(query: str, per_page: int) -> str`
- Produces: `parse_repository_item(item: dict, *, source_id: str, discovery_route: str, matched_watch_lines: list[str], observed_at: str) -> dict`
- Produces: `collect_github_queries(config: dict, *, token: str | None, observed_at: str, opener=urlopen) -> tuple[list[dict], list[dict]]`

- [ ] **Step 1: Write failing tests using fixed GitHub API JSON fixtures; no network in tests.**
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Implement URL construction, parsing, bounded requests, and per-query `ok|partial|failed` health.**
- [ ] **Step 4: Verify GREEN and full test suite.**
- [ ] **Step 5: Commit Task 2.**

### Task 3: Snapshot writer and previous-state comparison

**Files:**
- Create: `needle_watch/storage.py`
- Create: `tests/test_storage.py`

**Interfaces:**
- Produces: `load_prior_candidate_ids(path: Path) -> set[str]`
- Produces: `write_receipt_snapshot(receipt: dict, *, repo_root: Path, date_key: str) -> tuple[Path, Path]`
- Guarantee: dated and latest bytes are identical.

- [ ] **Step 1: Write failing tests for absent prior file, prior ID loading, deterministic bytes, and identical dated/latest snapshots.**
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Implement minimal storage functions.**
- [ ] **Step 4: Verify GREEN and full suite.**
- [ ] **Step 5: Commit Task 3.**

### Task 4: CLI collector

**Files:**
- Create: `scripts/collect-needle-watch.py`
- Create: `tests/test_collect_cli.py`

**Interfaces:**
- Consumes: `config/needle-watch.json`, optional `GITHUB_TOKEN`, optional GitHub Actions environment IDs.
- Produces: dated/latest receipt files and terminal summary `NEEDLE_WATCH_RECEIPT PASS ...` or nonzero failure.

- [ ] **Step 1: Write failing CLI test against a temporary repo using an injected fixture source mode.**
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Implement CLI orchestration with no scientific filtering.**
- [ ] **Step 4: Verify GREEN and full suite.**
- [ ] **Step 5: Commit Task 4.**

### Task 5: GitHub Actions workflow and repository contract docs

**Files:**
- Create: `.github/workflows/needle-watch.yml`
- Create: `data/README.md`
- Modify: `README.md`

**Interfaces:**
- Workflow schedule: non-top-of-hour daily run plus `workflow_dispatch`.
- Workflow permissions: `contents: write` only where commit step requires it.
- Validation command: `python -m unittest discover -s tests -v` followed by collector execution and receipt validation.
- Commit scope: only `data/YYYY-MM-DD/needle-watch.json` and `data/latest/needle-watch.json`.

- [ ] **Step 1: Add a failing structural test asserting workflow schedule, permissions, test-before-collect ordering, and constrained git-add paths.**
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Add minimal workflow/docs satisfying the structural contract.**
- [ ] **Step 4: Verify GREEN and full suite.**
- [ ] **Step 5: Commit Task 5.**

### Task 6: Activation-gate verification

**Files:**
- Create: `tests/fixtures/null-day-source.json`
- Create: `docs/needle-watch-receipt.md`

**Interfaces:**
- A fixture run must produce `candidates: []` with healthy source records and `is_valid_null == true`.
- A failure fixture must produce `is_valid_null == false`.

- [ ] **Step 1: Write/extend failing tests for deliberate null-day vs source-failure distinction.**
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Add only the fixture/documentation needed to make the gate reproducible.**
- [ ] **Step 4: Run full suite and a local fixture collection; verify exact receipt bytes and required fields.**
- [ ] **Step 5: Push branch with MarcoPolo write profile, read back remote branch SHA/files, and record evidence in Issue #21.**
