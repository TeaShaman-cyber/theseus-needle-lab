# Needle realistic corrected-contract SFT — Stage B design

Date: 2026-09-01
Parent issue: #26
Status: DESIGN FOR REVIEW — NO TRAINING AUTHORIZED BY THIS DOCUMENT ALONE
Predecessor: `experiment/needle-semantic-verbalizer-preflight` at `986840f6a1b59ed48e12bb85f5bbf30e26db963a`

## 1. Purpose

Stage B asks one bounded question:

> With the already accepted Needle route-tool framing/schema contract, can an upstream-realistic supervised adaptation regime learn the `PROBE | READY | UNKNOWN` routing policy rather than merely changing tool-call priors?

This is a capability baseline, not a hyperparameter sweep and not a causal attribution study. The experiment deliberately changes the training regime from the prior 11-row/rank-4 micro-runs to a few-hundred-example/rank-16 regime while preserving the accepted interface contract.

A positive result means the stronger final-label SFT baseline can both fit the policy and improve held-out behavior without collapsing applicability. A negative result is also informative: it distinguishes persistent underfit from a train-fit/generalization gap.

## 2. Verified predecessor evidence

The design inherits the following verified constraints.

### 2.1 Accepted interface contract

From #12/#14 and Stage A of #26:

- tool name remains `route`;
- argument remains `decision`;
- enum remains uppercase `PROBE`, `READY`, `UNKNOWN`;
- schema serialization order remains `name -> parameters -> description`;
- route-positive queries use the exact prefix `Use route to classify the following evidence:\n\n`;
- route schema includes the accepted natural-language description;
- Stage A rejected `check / ready / unknown` because it reduced call reachability to 5/12 and collapsed 80% of semantic predictions to PROBE;
- Stage A rejected lowercase as the training target because its 5/12 apparent accuracy gain coincided with a 77.8% PROBE collapse;
- uppercase is retained because it is the least pathological semantically interpretable representation observed, not because its zero-shot accuracy is good.

The Stage A uppercase schema is frozen by behavior and exact bytes. During implementation, a committed contract snapshot must be tested byte-for-byte against `scripts/run_semantic_verbalizer_preflight.py::route_schema("A")` from predecessor `986840f6a1b59ed48e12bb85f5bbf30e26db963a`.

Observed predecessor digests:

```text
uppercase schema JSON SHA256
  e0892212cf97e9d728d8106f4c3fb35bbb09cf0a71bdd9a032b5f457a54ccb7a

route-positive prefix SHA256
  b8b1697130db2487e50125e2290cf623e3cc259a0647848b19bdf8c9fd465df7
```

### 2.2 Training-scale constraint

Pinned/current Needle guidance recorded in #4 says:

- default LoRA rank is 16;
- 200 examples × batch 16 × 3 epochs is only 39 steps and is described upstream as barely moving a rank-16 adapter;
- a few hundred clean examples should run roughly 10–30 epochs for tool-selection adaptation.

The strongest corrected prior run used only 11 effective training rows, rank 4, batch 2, 3 epochs, 18 optimizer steps.

### 2.3 Reproducibility constraint

From #1/#10:

- Needle 2.0.8 initializes LoRA with JAX seed 0;
- validation split uses deterministic NumPy RNG seed 0;
- epoch shuffle uses global `np.random.permutation` and is not seed-addressable through the public CLI;
- the previously verified wrapper seeds global NumPy before calling `needle.model.finetune.finetune_local`;
- even with that wrapper, separate GitHub runners can produce tiny float32 adapter differences and a one-prediction W4 behavior difference.

Therefore Stage B uses the established seeded wrapper pattern but does not claim byte-identical cross-run training. Two independent replicas are required for the quality claim.

### 2.4 Target-shape constraint

Needle 2.0.8 trains whole target sequences with token-level cross entropy. Earlier reasoning-rich targets dilute the decision branch and created truncation confounds.

Stage B therefore uses answer-only Needle targets. Human-readable rationales remain in the semantic source dataset but are not projected into `reasoning` or `system` fields in the training JSONL.

This makes Stage B a clean final-label SFT baseline. It does not test process supervision; #6 remains downstream for that comparison.

## 3. Non-goals

Stage B does not:

- change the Needle trainer;
- introduce LlamaFactory, TRL, Unsloth, PEFT, Axolotl, or teacher distillation;
- use OpenRouter or `needle finetune --generate`;
- ingest private conversations or private corpora;
- search a hyperparameter grid;
- claim exact adapter-byte reproducibility across runners;
- infer that training-scale changes alone caused any improvement;
- create a GitHub Release before the result is accepted;
- add artifact attestations before the first accepted release-worthy bundle exists.

## 4. Dataset architecture

The dataset has two layers:

```text
repo-authored semantic family spec
          ↓ deterministic expansion
exact semantic cases
          ↓ deterministic Needle projection
train.needle.jsonl + heldout.eval.jsonl
          ↓
manifest + SHA256 bindings
```

The semantic layer is the human-reviewable source. The Needle JSONL is a projection.

No external model or web source generates Stage B examples. This deliberately avoids a source-evidence ambiguity in the baseline. Every source case is `synthetic_repo_authored` and is reconstructable from versioned repository data and the deterministic compiler.

### 4.1 Proposed files

```text
experiments/needle-realistic-sft/
├── README.md
├── contract/
│   ├── route-schema.json
│   ├── route-positive-prefix.txt
│   └── training-config.json
├── source/
│   ├── families.json
│   └── semantic-cases.jsonl
├── data/
│   ├── train.needle.jsonl
│   └── heldout.eval.jsonl
├── manifests/
│   ├── dataset-manifest.json
│   └── heldout-manifest.json
└── receipts/
    └── README.md

scripts/
├── build_realistic_sft_dataset.py
├── validate_realistic_sft_dataset.py
├── run_seeded_finetune.py
├── run_realistic_sft_eval.py
└── realistic_sft_receipt.py

.github/workflows/
├── needle-realistic-sft-contract.yml
└── needle-realistic-sft.yml
```

The existing `run_seeded_finetune.py` implementation from the verified #10 branch is reused or copied exactly before any extension. Any change to its seeding behavior requires its own test and explicit receipt field.

## 5. Dataset geometry

### 5.1 Training set

The final training projection contains exactly 360 examples:

```text
100 PROBE route-positive
100 READY route-positive
100 UNKNOWN route-positive
 60 route-negative / answers: []
---
360 total
```

Positive decision classes are exactly balanced. Negatives are a separate applicability class and are never remapped to `UNKNOWN`.

Training uses 18 semantic families:

#### PROBE — five families, 20 examples each

1. `probe.stale_runtime_safe_version_probe`
2. `probe.stale_auth_safe_permission_probe`
3. `probe.incomplete_search_safe_scope_expand`
4. `probe.cached_provider_state_safe_status_query`
5. `probe.artifact_pointer_safe_digest_readback`

#### READY — five families, 20 examples each

1. `ready.fresh_runtime_identity_verified`
2. `ready.exact_persistence_readback_match`
3. `ready.exact_sha_ci_postcondition_success`
4. `ready.current_authoritative_provider_response`
5. `ready.artifact_integrity_hash_verified`

#### UNKNOWN — five families, 20 examples each

1. `unknown.stale_conflicting_snapshots_no_probe`
2. `unknown.authority_unreachable_no_safe_probe`
3. `unknown.missing_private_source_inaccessible`
4. `unknown.expired_ephemeral_evidence_unrecoverable`
5. `unknown.ambiguous_runtime_identity_no_discriminator`

#### Route-negative — three families, 20 examples each

1. `negative.creative_writing`
2. `negative.generic_knowledge_math`
3. `negative.translation_summarization`

Each 20-example training family expands deterministically as four independently authored phrasings × five neutral entity/provider/tool substitutions. The compiler must reject duplicate final query strings.

Entity substitutions are intentionally cross-class: the same provider/tool/entity vocabulary appears in multiple decision classes so the class cannot be inferred from a provider name alone.

### 5.2 Held-out set

The held-out set contains exactly 96 examples from eight families that do not appear in training:

```text
24 PROBE
24 READY
24 UNKNOWN
24 route-negative
---
96 total
```

Held-out families:

#### PROBE — two families, 12 examples each

- `probe.provider_migration_current_endpoint_probe`
- `probe.package_version_current_install_probe`

#### READY — two families, 12 examples each

- `ready.signed_receipt_current_readback`
- `ready.live_health_check_authority_match`

#### UNKNOWN — two families, 12 examples each

- `unknown.irreconcilable_logs_probe_prohibited`
- `unknown.missing_capability_probe_would_mutate`

#### Route-negative — two families, 12 examples each

- `negative.code_formatting_request`
- `negative.social_smalltalk_request`

Each held-out family expands as three independently authored phrasings × four entity substitutions.

### 5.3 Leakage barriers

Validation must fail if any of these are true:

- a family ID occurs in both train and held-out;
- a final query string occurs in both train and held-out;
- a case ID is duplicated;
- positive class counts are not exactly 100/100/100 in train;
- held-out class counts are not exactly 24/24/24 plus 24 negatives;
- an entity vocabulary item appears in only one positive decision class when the manifest marks it as a shared neutral entity;
- a negative case has a route answer;
- a positive case lacks exactly one route answer.

## 6. Semantic source contract

Each expanded semantic source record contains at minimum:

```json
{
  "case_id": "train-probe-stale-runtime-001",
  "family_id": "probe.stale_runtime_safe_version_probe",
  "split": "train | heldout",
  "applicability": "route | none",
  "expected_decision": "PROBE | READY | UNKNOWN | null",
  "semantic_rule": "stale capability evidence plus a safe current discriminator implies PROBE",
  "query": "A cached runtime note is stale and a harmless current version check is available.",
  "rationale": "Current verification is needed and can be performed safely.",
  "derivation_family": "stale-runtime-v1",
  "entity_variant": "runtime-alpha",
  "schema_contract": "needle-route-uppercase-v1",
  "source_kind": "synthetic_repo_authored"
}
```

`rationale` is audit metadata. It is not copied into the Needle training target.

No field containing a hidden label hint may be injected into the model-visible query.

## 7. Needle projection contract

### 7.1 Route-positive examples

For positive examples:

- prepend the exact accepted classification prefix;
- include the exact accepted described `route` schema;
- emit exactly one answer with one `decision` value;
- omit `reasoning` and `system` from the projected training row.

Conceptually:

```json
{
  "query": "Use route to classify the following evidence:\n\n<source query>",
  "tools": ["<exact accepted route schema>"],
  "answers": [
    {"name": "route", "arguments": {"decision": "PROBE"}}
  ]
}
```

### 7.2 Route-negative examples

For negative examples:

- expose the same exact route tool schema;
- do not add the classification prefix;
- keep the user query as an unrelated request;
- emit `answers: []`;
- omit `reasoning` and `system`.

This preserves the Glaive-style distinction between an available tool and a tool that is actually applicable.

A negative is not `UNKNOWN`. `UNKNOWN` is a route-positive policy decision meaning insufficient evidence and no safe current probe; `NO_CALL` means the route tool is not the appropriate tool for the request at all.

## 8. Token-length and truncation gate

Training cap is fixed at:

```text
max_len = 256
```

Before any finetune job, a pinned Needle 2.0.8 tokenizer audit must reconstruct every projected training sequence and prove that no example loses target tokens or EOS at cap 256.

If any row would truncate:

```text
DATASET_CONTRACT = FAIL_TARGET_TRUNCATION
```

The row must be rewritten or removed through a reviewed dataset change. The workflow must not silently increase `max_len` to make the gate green.

The manifest records:

- per-row source-token count;
- per-row target-token count;
- total sequence length;
- effective maximum sequence length;
- tokenizer model identity/digest where available;
- truncated row list, which must be empty.

## 9. Frozen training configuration

The full quality run uses exactly:

```text
cactus-needle       2.0.8
base checkpoint     exact Needle 2 checkpoint already pinned in #1
numpy shuffle seed  0 via verified seeded wrapper
examples            360
val_split           0.10
batch_size          16
lr                  1e-4
lora_rank           16
lora_alpha          32
max_len             256
epochs              15
generate             0
workers              1
```

With 360 rows and `val_split=0.10`, Needle deterministically holds out 36 internal optimization-validation rows and trains on 324 rows.

Expected optimizer geometry:

```text
steps_per_epoch = ceil(324 / 16) = 21
total_steps     = 15 * 21 = 315
warmup_steps    = floor(315 / 20) = 15
schedule        = Needle 2.0.8 warmup + cosine decay
optimizer       = Needle 2.0.8 clip(1.0) + AdamW
```

The 36 internal validation rows are not the scientific held-out set. Scientific evaluation uses the separate 96-case held-out manifest.

## 10. Runtime/resource gate

The old 12-row smoke measured 23.59 seconds for 6 steps, but scaling to rank 16, batch 16, and longer sequences is unknown. No linear extrapolation is treated as fact.

After the dataset/config/held-out manifests are committed and reviewed, but before the two full replicas, run one resource-only dry-run:

```text
same 360-row dataset
same rank/batch/lr/alpha/max_len/seed
same pinned runtime
same val_split
epochs = 1 ONLY for resource measurement
```

This dry-run is explicitly not model-quality evidence.

Proceed to the full replicas only if the dry-run completes with:

```text
wall time <= 8 minutes
peak RSS  <= 12 GiB
no disk exhaustion
no target truncation
no runtime/API drift
```

If the resource gate fails, stop with `BLOCKED_RESOURCE_ENVELOPE` and revise the reviewed design/config before another quality run.

## 11. Execution topology

### 11.1 Contract workflow

`needle-realistic-sft-contract.yml` runs on pushes to the Stage B branch and contains no finetune command.

It must:

1. run repository tests;
2. deterministically build/validate the dataset projections;
3. assert exact Stage A schema/prefix inheritance;
4. run the pinned tokenizer/truncation audit;
5. verify train/held-out family separation and class counts;
6. verify committed projections/manifests match a clean rebuild;
7. perform privacy/public-data checks.

### 11.2 Training workflow

`needle-realistic-sft.yml` is `workflow_dispatch` only. A push must never start a quality training run automatically.

It exposes an explicit mode:

```text
mode = resource_dry_run | full
```

`resource_dry_run` runs one one-epoch resource probe.

`full` runs two independent replicas, `R1` and `R2`, with identical dataset/config/seed on independent GitHub-hosted jobs. The replicas are replication evidence, not different hyperparameters.

Permissions remain least privilege and secret-free:

```text
contents: read
```

No OpenRouter key or other provider secret is accepted by this workflow.

## 12. Artifact contract

Each full replica produces at minimum:

```text
adapter-rN.pkl
tuned-rN.cact
training log
package/runtime versions
resource metrics
train replay predictions
held-out predictions
artifact SHA256s
```

Canonical tuned inference artifact is built with the pinned Needle 2.0.8 default build path:

```text
needle build <base-checkpoint> --lora adapter-rN.pkl --out tuned-rN.cact
```

No `--bits` override is part of the primary Stage B comparison. Uniform W4 may be generated later as a diagnostic, but it is not required to decide whether the policy learned.

GitHub Actions artifacts are retention-bound transport/evidence copies, not canonical archival authority.

## 13. Evaluation contract

Evaluate three distinct scopes separately.

### 13.1 Route-positive train replay

Use the 300 positive training cases only for decision mapping metrics:

- valid route call rate;
- decision accuracy;
- per-class confusion matrix;
- prediction distribution;
- dominant-class rate.

### 13.2 Training negative controls

Use the 60 training negatives separately:

- NO_CALL rate;
- invalid-call rate;
- accidental route-call distribution.

Do not mix negatives into decision accuracy.

### 13.3 Scientific held-out set

Use all 96 held-out cases, reporting separately:

- 72 route-positive decision cases;
- 24 route-negative applicability controls.

Compare:

```text
base model
vs replica R1
vs replica R2
```

Base and both tuned artifacts must use identical held-out queries/schema/framing within the relevant applicability class.

## 14. Pre-registered dispositions

The experiment does not use a single scalar score.

### 14.1 `ACCEPTED_LEARNED_AND_GENERALIZES`

Both R1 and R2 must satisfy all of the following:

1. positive train replay decision accuracy >= 70%;
2. held-out positive decision accuracy improves by at least 6 correct cases out of 72 relative to base;
3. held-out positive route-call reachability is not worse than base by more than 3 cases out of 72;
4. held-out negative NO_CALL count is not worse than base by more than 2 cases out of 24;
5. dominant semantic decision among valid held-out positive route calls is <= 70%;
6. no privacy/provenance/runtime contract failure occurs.

The +6/72 requirement is deliberately larger than the previously observed one-prediction cross-run W4 noise floor and must hold independently in both replicas.

### 14.2 `INCONCLUSIVE_TRAIN_FIT_GENERALIZATION_GAP`

Use this disposition when both replicas reach >=70% positive train replay accuracy but the held-out acceptance criteria above do not hold in both replicas, while applicability/negative controls do not catastrophically regress.

This outcome means the stronger final-label SFT can fit the training policy but has not demonstrated robust family-level generalization.

### 14.3 `REJECTED_PERSISTENT_UNDERFIT`

Use this disposition when both replicas remain below 70% positive train replay decision accuracy.

This means upstream-realistic scale was still insufficient to fit the bounded mapping under this final-label contract.

### 14.4 `REJECTED_APPLICABILITY_REGRESSION`

Use this disposition if either replica gains decision accuracy only by materially damaging route-call reachability or negative-control NO_CALL behavior beyond the thresholds above.

### 14.5 `INCONCLUSIVE_REPLICA_DIVERGENCE`

Use this disposition when only one of two replicas satisfies the learned/generalizes criteria.

Do not average the two replicas into a success claim.

## 15. Receipts and provenance

The final receipt binds:

- parent Issue #26;
- exact source commit;
- predecessor Stage A commit;
- pinned package/runtime versions;
- base checkpoint hash;
- exact schema/prefix hashes;
- family spec hash;
- expanded semantic dataset hash;
- projected train/held-out hashes;
- training-config hash;
- tokenizer/truncation report hash;
- R1/R2 adapter and `.cact` hashes;
- prediction-vector hashes;
- resource metrics;
- all acceptance thresholds and computed disposition.

Because the baseline uses only repo-authored synthetic source material, it does not claim external raw-fetch provenance. If a later dataset uses teacher or fetched external material, #21's distinction applies:

```text
dataset integrity != source-evidence integrity
```

A normalized row digest alone is not proof of the raw external source.

## 16. Privacy classification

Stage B is PUBLIC / SYNTHETIC ONLY.

Prohibited inputs:

- raw user conversation text;
- private session-search artifacts;
- credentials or auth tokens;
- private repository contents;
- private provider responses;
- personal identifiers copied from real sessions.

Entity/provider/tool names used for lexical variation must be generic synthetic names or public project-neutral names approved by the dataset validator.

## 17. GitHub Release boundary

No Release is created by the Stage B implementation or training workflow automatically.

If and only if the final disposition is `ACCEPTED_LEARNED_AND_GENERALIZES`, the result becomes eligible for the next separately verified packaging step.

Candidate first Needle research Release:

```text
tag: needle-policy-sft-v0.1
```

Candidate bundle:

```text
adapter-r1.pkl
adapter-r2.pkl
tuned-r1.cact
tuned-r2.cact
dataset-manifest.json
heldout-manifest.json
training-config.json
verification-receipt.json
SHA256SUMS
```

Both replicas remain in the bundle; Stage B does not arbitrarily declare one replica canonical merely because it ran first.

A later artifact-attestation pilot may cryptographically bind this release bundle to repository/workflow/commit provenance. That attestation supplements the Theseus research receipt and does not replace its interpretation or source-evidence semantics.

## 18. Implementation/testing strategy

Implementation follows TDD.

At minimum tests must prove:

1. exact Stage A schema/prefix inheritance;
2. exact 360/96 dataset geometry;
3. exact positive class balance;
4. family/query leakage barriers;
5. positive vs negative projection semantics;
6. no reasoning/system leakage into Needle training rows;
7. max_len=256 no-truncation gate;
8. deterministic clean rebuild hashes;
9. exact frozen training-config fields;
10. seeded wrapper uses global NumPy seed before `finetune_local`;
11. contract workflow contains no finetune command;
12. training workflow cannot trigger on push;
13. full mode launches exactly two equal-config replicas;
14. receipt computes train/held-out/applicability metrics separately;
15. all five pre-registered dispositions are mechanically testable;
16. public-data/privacy scan rejects forbidden markers.

## 19. Execution gate

Before any Stage B finetune command runs, the repository must contain and review:

- this approved design;
- exact family spec;
- exact expanded semantic cases;
- exact projected train/held-out datasets;
- exact dataset/held-out manifests;
- exact training-config JSON;
- static tokenizer/truncation report proving zero truncation;
- privacy/public-data validation;
- success/failure thresholds from this design.

Only after those postconditions are observed may Issue #26 move from `Specified` to `Running` and the resource dry-run execute.

## 20. Expected causal value

Stage B is designed to answer the next highest-information question left by #12/#14/#16/#18:

```text
correct interface contract
+ semantically meaningful labels
+ clean positive/negative applicability supervision
+ few-hundred-example scale
+ rank-16 / hundreds of optimizer steps
                 ↓
can Needle fit and generalize the routing policy?
```

If yes, #6 gains a strong final-label SFT baseline against which teacher/process/on-policy supervision can be compared.

If no, repeated rank-4 micro-training is no longer a serious explanation path; attention should move toward objective/target structure, process supervision, or a model-capacity/task-factorization limit.
