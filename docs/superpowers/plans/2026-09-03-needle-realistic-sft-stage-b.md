# Needle Realistic SFT Stage B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and validate the deterministic Stage B semantic dataset, Needle projection, manifests, and contract workflow without running finetuning.

**Architecture:** Repository-authored semantic family definitions are the authority. A deterministic Python compiler expands those definitions into exact semantic cases, projects them into the frozen Needle route-tool contract, and writes manifests binding source/projection bytes. Validation fails closed on geometry, leakage, label hints, truncation prerequisites, or provenance violations.

**Tech Stack:** Python 3 stdlib, unittest, JSON/JSONL, GitHub Actions YAML.

**Spec:** `docs/superpowers/specs/2026-09-01-needle-realistic-sft-stage-b-design.md`

## Global Constraints

- No Stage B finetune runs in this plan.
- Training geometry is exactly 360 rows: 100 PROBE, 100 READY, 100 UNKNOWN, 60 route-negative.
- Scientific held-out geometry is exactly 96 rows: 24 PROBE, 24 READY, 24 UNKNOWN, 24 route-negative.
- Source records use `source_kind=synthetic_repo_authored`; watcher/CI and external sources never enter baseline train/held-out data.
- Positive Needle rows use the frozen uppercase `PROBE | READY | UNKNOWN` route schema and accepted classification prefix.
- Negative rows expose the same route tool but use `answers: []` and no classification prefix.
- Semantic rationales remain audit metadata and never enter model-visible projections.
- Generated files are deterministic stable JSON/JSONL with SHA256 bindings.
- Validation fails if train/held-out family IDs overlap, queries overlap, case IDs duplicate, class geometry differs, or negative/positive answer cardinality violates the contract.
- External challenge evidence remains post-baseline and requires exact raw-byte evidence per the design; this plan only enforces that baseline sources are repository-authored.

---

### Task 1: Deterministic semantic source expansion

**Files:**
- Create: `experiments/needle-realistic-sft/source/families.json`
- Create: `scripts/build_realistic_sft_dataset.py`
- Create: `tests/test_realistic_sft_dataset.py`

**Interfaces:**
- Consumes: versioned family definitions in `families.json`.
- Produces: `build_semantic_cases(families: dict) -> tuple[list[dict], list[dict]]` returning exact train and held-out semantic records.

- [ ] **Step 1: Write failing geometry/source tests**

Add tests asserting exactly 360 train and 96 held-out records, exact per-class counts, unique case IDs/queries, disjoint train/held-out family IDs, and `source_kind == "synthetic_repo_authored"` for every record.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python3 -m unittest tests.test_realistic_sft_dataset -v`
Expected: FAIL because `scripts.build_realistic_sft_dataset` and family definitions do not exist.

- [ ] **Step 3: Implement minimal family expansion**

Implement stable loading and deterministic expansion. Each training family expands to four authored phrasing templates × five neutral entities; each held-out family expands to three templates × four neutral entities. Family definitions contain `family_id`, `split`, `applicability`, `expected_decision`, `semantic_rule`, `derivation_family`, authored `phrases`, and neutral `entities`. Expansion formats phrases with `{entity}` and emits deterministic `case_id` values.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python3 -m unittest tests.test_realistic_sft_dataset -v`
Expected: all Task 1 tests PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add deterministic Stage B semantic dataset source (refs #26)`

### Task 2: Frozen Needle projection and deterministic manifests

**Files:**
- Modify: `scripts/build_realistic_sft_dataset.py`
- Modify: `tests/test_realistic_sft_dataset.py`
- Create: `experiments/needle-realistic-sft/contract/route-schema.json`
- Create: `experiments/needle-realistic-sft/contract/route-positive-prefix.txt`
- Create: `experiments/needle-realistic-sft/contract/training-config.json`
- Generate: `experiments/needle-realistic-sft/source/semantic-cases.jsonl`
- Generate: `experiments/needle-realistic-sft/data/train.needle.jsonl`
- Generate: `experiments/needle-realistic-sft/data/heldout.eval.jsonl`
- Generate: `experiments/needle-realistic-sft/manifests/dataset-manifest.json`
- Generate: `experiments/needle-realistic-sft/manifests/heldout-manifest.json`

**Interfaces:**
- Consumes: semantic records from Task 1 and exact frozen route contract bytes.
- Produces: `project_needle_case(record: dict, schema: dict, prefix: str) -> dict`, deterministic generated files, SHA256 manifest bindings.

- [ ] **Step 1: Write failing projection tests**

Assert positive rows contain the exact prefix, exactly one route answer, uppercase decision, no rationale/reasoning/system leakage; negative rows contain no prefix, the same schema, and `answers: []`. Assert generated output is byte-stable across two clean builds and manifests bind each generated file by SHA256 and row count.

- [ ] **Step 2: Verify RED**

Run: `python3 -m unittest tests.test_realistic_sft_dataset -v`
Expected: new projection/manifest tests FAIL because projection/build functions and contract files are missing.

- [ ] **Step 3: Implement projection and builder CLI**

Add stable JSON serialization using sorted keys and compact separators for hashes, newline-delimited stable JSON for JSONL, and a CLI `python3 scripts/build_realistic_sft_dataset.py --write`. The CLI writes all generated files atomically after validating semantic geometry.

- [ ] **Step 4: Generate files and verify GREEN**

Run:
`python3 scripts/build_realistic_sft_dataset.py --write`
`python3 -m unittest tests.test_realistic_sft_dataset -v`
Expected: all Task 1-2 tests PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add Stage B Needle projection and manifests (refs #26)`

### Task 3: Fail-closed validator and contract-only CI

**Files:**
- Create: `scripts/validate_realistic_sft_dataset.py`
- Modify: `tests/test_realistic_sft_dataset.py`
- Create: `.github/workflows/needle-realistic-sft-contract.yml`
- Create: `experiments/needle-realistic-sft/README.md`

**Interfaces:**
- Consumes: committed source, generated projections, manifests, and contract files.
- Produces: validator exit code 0 only when a clean rebuild exactly matches committed bytes and all baseline provenance/geometry gates pass.

- [ ] **Step 1: Write failing validator/workflow tests**

Tests must prove validator rejects an altered generated row, rejects an external `source_kind`, rejects train/held-out family overlap, and that workflow permissions are `contents: read` with no finetune command and runs repository tests + builder check + validator.

- [ ] **Step 2: Verify RED**

Run: `python3 -m unittest tests.test_realistic_sft_dataset -v`
Expected: validator/workflow tests FAIL because validator/workflow do not exist.

- [ ] **Step 3: Implement validator and workflow**

Validator loads committed files, rebuilds expected bytes in memory, checks exact equality and manifests, and exits non-zero with a specific contract error on any mismatch. Workflow runs on Stage B branch pushes/PRs and never invokes Needle finetuning.

- [ ] **Step 4: Verify GREEN and full regression suite**

Run:
`python3 scripts/build_realistic_sft_dataset.py --write`
`python3 scripts/validate_realistic_sft_dataset.py`
`python3 -m unittest discover -s tests -v`
`git diff --check`
Expected: validator PASS, all tests PASS, diff check clean.

- [ ] **Step 5: Commit**

Commit message: `ci: gate Needle Stage B dataset contract (refs #26)`

### Task 4: Remote review evidence

**Files:**
- No production file changes unless CI exposes a real defect; defects require a new failing test first.

**Interfaces:**
- Consumes: exact branch head after Tasks 1-3.
- Produces: pushed PR #28 head, GitHub Actions result, native GitHub readback evidence.

- [ ] **Step 1: Push the exact reviewed branch**

Push `experiment/needle-realistic-sft-spec` through the governed GitHub write profile.

- [ ] **Step 2: Read back PR head through the native GitHub connector**

Require PR #28 head SHA to equal local/remote branch SHA.

- [ ] **Step 3: Inspect contract workflow result**

Require repository tests and contract workflow to succeed on the exact head. If failure is implementation-related, reproduce with a failing local test before fixing.

- [ ] **Step 4: Record Stage B implementation checkpoint in Issue #26**

Record exact head SHA, generated geometry, manifest hashes, test count, CI run identity, and explicit `NO FINETUNE RUN` state.
