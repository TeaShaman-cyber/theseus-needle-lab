# Stage B Resource Gate Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the failed 480-second preregistered wall gate while separating scientific resource validity from heterogeneous hosted-runner capacity planning.

**Architecture:** Receipt v3 keeps hard scientific gates for truncation, execution, RSS, disk, and pinned input/runtime identity. Hosted-runner wall time becomes diagnostic capacity evidence with a 15-epoch projection, 1.20 planning margin, and a 210-minute planned quality-job budget. Existing immutable v2 evidence may be deterministically reclassified because the revision changes interpretation, not measurement.

**Tech Stack:** Python 3, unittest, GitHub Actions, JSON receipts.

**Spec:** `docs/superpowers/specs/2026-09-01-needle-realistic-sft-stage-b-design.md`

## Global Constraints

- Preserve the observed 480-second failure as historical preregistered evidence.
- Do not reinterpret resource evidence as model-quality evidence.
- Do not run another finetune merely to apply the revised classification rule.
- Quality replicas remain manual-only and exact-SHA bound.
- Peak RSS hard limit remains 12 GiB.
- Planned full-replica timeout is 210 minutes.

---

### Task 1: Receipt v3 scientific/capacity split

**Files:**
- Modify: `scripts/realistic_sft_resource_receipt.py`
- Modify: `scripts/run_realistic_sft_resource_dry_run.sh`
- Test: `tests/test_realistic_sft_dataset.py`

**Interfaces:**
- Consumes: measured GNU-time/RSS/disk/token-audit evidence.
- Produces: receipt v3 with `scientific_validity`, `historical_preregistered_wall_gate`, and `operational_capacity`.

- [x] Write RED tests for slow-but-scientifically-valid hosted-runner evidence.
- [x] Implement receipt v3.
- [x] Require both scientific PASS and capacity FITS before resource authorization.
- [x] Run full repository tests.

### Task 2: Design revision and historical preservation

**Files:**
- Modify: `docs/superpowers/specs/2026-09-01-needle-realistic-sft-stage-b-design.md`

**Interfaces:**
- Consumes: observed 326.81 s and 594.93 s resource measurements.
- Produces: explicit post-result design revision that does not rewrite the original preregistration.

- [x] Record scientific vs operational gate semantics.
- [x] Record 210-minute quality-job capacity budget.
- [ ] Publish exact branch head and verify PR #28 readback.

### Task 3: Reclassify immutable corrected resource evidence

**Files:**
- No training data or model files change.

**Interfaces:**
- Consumes: immutable run `33716826568` resource metrics/artifact.
- Produces: a v3 classification/checkpoint in Issue #26 without rerunning training.

- [ ] Recompute receipt v3 classification from preserved v2 measured metrics.
- [ ] Confirm scientific gate PASS, historical 480-second gate FAIL, and capacity FITS.
- [ ] Record revision checkpoint in Issue #26 with source run/artifact digest.
