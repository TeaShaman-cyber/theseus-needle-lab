# Stage B Resource Provenance Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Stage B resource dry-run receipt bind the exact experiment commit separately from the launcher commit and persist the complete evidence bundle as a GitHub Actions artifact.

**Architecture:** The experiment entrypoint receives `EXPERIMENT_SHA` and `LAUNCHER_SHA` explicitly and emits receipt schema v2 with both identities. The default-branch manual launcher verifies the requested experiment SHA against the allowed branch head, checks out that exact SHA, passes both identities to the fixed entrypoint, and uploads `artifacts/`, `results/`, `logs/`, and `metrics/` with `if: always()`.

**Tech Stack:** Bash, Python 3.11, GitHub Actions, cactus-needle 2.0.8, unittest.

**Spec:** `docs/superpowers/specs/2026-09-01-needle-realistic-sft-stage-b-design.md`

## Global Constraints

- Resource probe remains exactly one epoch and is not model-quality evidence.
- Exact experiment SHA must equal current head of `experiment/needle-realistic-sft-spec` before execution.
- Receipt must distinguish launcher identity from experiment identity.
- Evidence bundle upload is mandatory even when the resource entrypoint fails.
- Quality replicas remain blocked until corrected resource evidence is independently read back.

---

### Task 1: Receipt identity contract v2

**Files:**
- Modify: `scripts/realistic_sft_resource_receipt.py`
- Modify: `scripts/run_realistic_sft_resource_dry_run.sh`
- Modify: `tests/test_realistic_sft_dataset.py`

**Interfaces:**
- Consumes: explicit `EXPERIMENT_SHA`, `LAUNCHER_SHA`, and `GITHUB_RUN_ID`.
- Produces: `theseus.needle.realistic_sft_resource_dry_run.v2` with `source.experiment_commit`, `source.launcher_commit`, `source.workflow_run_id`.

- [ ] Write failing tests for distinct experiment/launcher identities and required entrypoint environment.
- [ ] Run focused tests and confirm RED for the old v1 contract.
- [ ] Implement minimal receipt v2 and explicit entrypoint arguments.
- [ ] Run focused tests and full suite; confirm GREEN.
- [ ] Commit and publish exact experiment head.

### Task 2: Default-branch launcher evidence durability

**Files:**
- Modify: `.github/workflows/needle-stage-b-dispatch.yml` on a main-based worktree.
- Modify: `tests/test_stage_b_dispatch_launcher.py`.

**Interfaces:**
- Consumes: manual `experiment_sha` input.
- Produces: explicit `EXPERIMENT_SHA`/`LAUNCHER_SHA` environment and durable `needle-stage-b-resource-<run_id>` artifact bundle.

- [ ] Write failing launcher test for identity propagation and `if: always()` artifact upload.
- [ ] Confirm RED on current main launcher.
- [ ] Implement minimal launcher change using pinned `actions/upload-artifact`.
- [ ] Run launcher/full main tests and confirm GREEN.
- [ ] Publish PR, require green Docs check, merge to main.

### Task 3: Corrected resource rerun and readback

**Files:** no source changes expected.

**Interfaces:**
- Consumes: exact published experiment SHA and merged launcher.
- Produces: completed workflow run plus downloadable evidence artifact whose receipt identities and hashes are independently verified.

- [ ] Dispatch launcher with exact current experiment SHA.
- [ ] Verify SHA guard, exact checkout, and entrypoint execution.
- [ ] Fetch workflow artifact and inspect `resource-receipt.json`.
- [ ] Verify `experiment_commit` equals requested experiment SHA and `launcher_commit` equals workflow head SHA.
- [ ] Verify resource disposition, token audit, input hashes, adapter hash, wall time, RSS, and artifact presence.
- [ ] Record corrected checkpoint in Issue #26; only then decide whether quality replicas are unblocked.
