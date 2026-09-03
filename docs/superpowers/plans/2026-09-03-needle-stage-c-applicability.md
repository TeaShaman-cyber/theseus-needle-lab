# Needle Stage C Applicability Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a preregistered Stage C A/B experiment that recovers NO_CALL applicability using bounded hard-negative recovery state without sacrificing Stage B positive gains.

**Architecture:** Preserve Stage B as an immutable reference. Add a sibling Stage C experiment that derives canonical recovery state from train-side failures only, deterministically projects two equal-budget training arms, evaluates applicability and semantic routing as separate gates, and emits reproducible receipts.

**Tech Stack:** Python 3.12, unittest, JSON/JSONL, cactus-needle 2.0.8, GitHub Actions manual dispatch.

**Spec:** `docs/superpowers/specs/2026-09-03-needle-stage-c-applicability-design.md`

## Global Constraints

- Stage B datasets, scripts, receipts, and accepted digests are immutable references.
- Heldout cases MUST never enter recovery state or sampling decisions.
- Arm A and Arm B use the same base checkpoint, positive examples, heldout set, training budget, seeds, and evaluation harness.
- Canonical decision state uses enums only and contains no free-form rationale.
- Applicability is factorized as `NONE|ROUTE`; semantic routing is `PROBE|READY|UNKNOWN` only when applicability is `ROUTE`.
- Recovery priority rises after `FALSE_CALL` and decays only after preregistered stable success.
- Acceptance requires heldout negative `NO_CALL >= 20/24`, heldout positive correct `>= 32/72`, dominant semantic decision rate `<= 0.70`, and both replicas meeting the registered gates.
- No production or external provider mutations are required to build or unit-test Stage C.

---

### Task 1: Canonical recovery-state model

**Files:**
- Create: `scripts/stage_c_recovery_state.py`
- Create: `tests/test_stage_c_recovery_state.py`
- Create: `experiments/needle-stage-c-applicability/contract/recovery-policy.json`

**Interfaces:**
- Consumes Stage B semantic train rows and train-side evaluation outcomes.
- Produces `build_recovery_state(semantic_rows, outcome_rows, policy) -> list[dict]` and deterministic JSON state.

- [ ] Write failing tests proving heldout rows are rejected, `FALSE_CALL` increments failure count/priority, correct NO_CALL advances success streak/decay, and enum/state invariants are strict.
- [ ] Run `python3 -m unittest tests.test_stage_c_recovery_state -v`; expected RED because module does not exist.
- [ ] Implement minimal pure functions and a frozen policy with exact priority/decay constants.
- [ ] Re-run targeted tests; expected PASS.
- [ ] Run full suite; expected all prior tests plus Stage C tests PASS.
- [ ] Commit `feat: add Stage C recovery state model`.

### Task 2: Deterministic equal-budget Arm A / Arm B projection

**Files:**
- Create: `scripts/build_stage_c_dataset.py`
- Create: `tests/test_stage_c_dataset.py`
- Create generated contract/manifests under `experiments/needle-stage-c-applicability/`.

**Interfaces:**
- Consumes frozen Stage B train semantic rows plus Task 1 recovery state.
- Produces exact-byte `arm-a.train.needle.jsonl`, `arm-b.train.needle.jsonl`, canonical-state JSON, and manifests binding source SHA256 values.

- [ ] Write failing tests proving no heldout case IDs appear, identical total training rows/budget across arms, identical positive multiset, Arm A uses ordinary negative replay, Arm B reallocates only negative sampling by recovery priority, and canonical targets factorize applicability before semantic decision.
- [ ] Run targeted dataset tests; expected RED.
- [ ] Implement deterministic projection with fixed seed/order and explicit multiplicity accounting.
- [ ] Re-run targeted tests; expected PASS.
- [ ] Add byte-stability and manifest binding tests.
- [ ] Run full suite.
- [ ] Commit `feat: build deterministic Stage C A-B datasets`.

### Task 3: Factorized evaluation and preregistered receipt

**Files:**
- Create: `scripts/stage_c_quality_receipt.py`
- Create: `tests/test_stage_c_quality.py`
- Reuse: `scripts/run_realistic_sft_eval.py` output format where possible.

**Interfaces:**
- Consumes per-case base/Arm-A/Arm-B evaluation JSONL for train and heldout plus recovery-state metadata.
- Produces per-arm metrics separating applicability gate from semantic decision accuracy and a two-replica Stage C disposition.

- [ ] Write failing tests for applicability confusion (`NONE/ROUTE`), semantic confusion (`PROBE/READY/UNKNOWN` on route-only cases), heldout negative floor `20/24`, positive floor `32/72`, dominant semantic rate `<=0.70`, and explicit failure dispositions.
- [ ] Run targeted tests; expected RED.
- [ ] Implement minimal metric and receipt functions with integer acceptance gates.
- [ ] Add test proving applicability failure cannot be hidden by semantic accuracy.
- [ ] Add test proving both replicas are required.
- [ ] Run full suite.
- [ ] Commit `feat: add Stage C factorized quality receipt`.

### Task 4: Bounded training/eval entrypoints and manual launcher

**Files:**
- Create: `scripts/run_stage_c_full_train.sh`
- Create: `scripts/run_stage_c_full_eval.sh`
- Create: `.github/workflows/needle-stage-c-dispatch.yml`
- Create: `tests/test_stage_c_full_contract.py`

**Interfaces:**
- Consumes exact Stage C experiment SHA and arm/replica matrix.
- Produces arm-scoped adapters/cact files, train receipts, eval JSONL, replica receipts, and final A/B comparison receipt.

- [ ] Write failing contract tests proving manual-only dispatch, exact-head gate, read-only GitHub permission, fixed entrypoints, arms `[A,B]`, replicas `[R1,R2]`, pinned cactus-needle `2.0.8`, same training hyperparameters, and no arbitrary command input.
- [ ] Run targeted tests; expected RED.
- [ ] Implement minimal scripts by parameterizing the frozen Stage B train/eval pattern without modifying Stage B entrypoints.
- [ ] Re-run targeted tests; expected PASS.
- [ ] Run all unit tests and dataset validators.
- [ ] Run resource dry-run only; do not launch expensive full training until exact dataset/manifests and acceptance receipt code are reviewed.
- [ ] Commit `feat: add governed Stage C launcher`.

## Final verification before expensive run

- [ ] `python3 -m unittest discover -s tests -v` passes.
- [ ] Stage B generated artifacts/digests remain byte-identical.
- [ ] Arm A and Arm B manifests prove equal row/training budget and no heldout leakage.
- [ ] Recovery policy constants and sampling multiplicities are present in committed JSON, not runtime defaults.
- [ ] Exact experiment head is independently read back from remote.
- [ ] Resource dry-run passes before any full Stage C dispatch.
