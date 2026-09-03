# Needle Stage C Applicability Recovery Design

Date: 2026-09-03
Status: approved protocol, written-spec review pending
Parent research: #35, #36
Baseline experiment head: 7a5f75c

## Purpose

Test whether explicit applicability state plus recovery-focused hard-negative sampling can reverse the Stage B over-calling regression without sacrificing the positive heldout gain.

Stage C extends Stage B as a separate experiment. Stage B artifacts, route schema, heldout cases, evaluation semantics, and published disposition remain unchanged.

## Stage B failure being targeted

Observed reference behavior:

- positive heldout base: 21/72 correct;
- positive heldout tuned: 32/72 correct;
- heldout negatives NO_CALL: 24/24 base -> 0/24 tuned;
- train negatives NO_CALL: 60/60 -> 5/60 tuned;
- dominant heldout semantic decision rate: approximately 0.8889, above the 0.70 limit;
- final Stage B disposition: REJECTED_APPLICABILITY_REGRESSION.

The target is applicability recovery, not additional raw positive-call gain.

## Frozen A/B protocol

Two arms use the same base checkpoint, Stage B positive examples, heldout set, optimizer/training budget, evaluation harness, and replica policy.

### Arm A — append control

Add the Stage B hard negatives back into an ordinary training pool without recovery weighting or canonical applicability targets.

Purpose: distinguish recovery-specific effects from the trivial effect of showing the model more negative examples.

### Arm B — recovery treatment

Use all three mechanisms together:

1. hard-negative adaptive sampling;
2. explicit canonical decision state;
3. bounded recovery/recent buffer with scheduled weight decay.

No other scientific variable may intentionally differ from Arm A.

## Canonical decision state

Stage C introduces a repository-authored supervised state schema before the final route decision:

```json
{
  "tool_need": "required|helpful|unnecessary|unknown",
  "applicability_confidence_bin": "low|medium|high",
  "cost_class": "low|medium|high",
  "risk_class": "low|medium|high",
  "evidence_state": "sufficient|insufficient|conflicting",
  "decision": "NO_CALL|PROBE|CALL"
}
```

Constraints:

- fields are finite enums, not free-form rationale;
- no chain-of-thought or hidden reasoning target is introduced;
- canonical state is repository-authored and deterministic for every Stage C training case;
- evaluation continues to score observable routing behavior separately from canonical-state prediction;
- a model that predicts a plausible state but over-calls still fails applicability acceptance.

## Mapping to existing Stage B route behavior

Stage B observable route labels remain the behavioral authority:

- `NO_CALL` means no route tool call;
- `PROBE` maps to route decision `PROBE`;
- Stage B `READY` and `UNKNOWN` remain exact route decisions for behavioral evaluation.

The canonical `CALL` value means route invocation is applicable; the exact route semantic decision remains an independently scored field. Stage C must not collapse applicability and semantic decision accuracy into one metric.

## Recovery set

The initial recovery pool is derived only from known Stage B applicability failures, especially negative cases that tuned Stage B changed from correct `NO_CALL` to a route call.

The heldout set remains held out. Its labels may define the preregistered failure class, but heldout query text must not be copied into Stage C training.

Training recovery examples must come from train-side negative families or newly repository-authored sibling families that preserve family-level separation from heldout.

## Adaptive sampling policy

Arm B uses a bounded deterministic schedule, not online stochastic reward hacking.

- recovery examples receive elevated sampling weight in the early phase;
- ordinary positive and negative examples remain present throughout training;
- recovery weight decays in a preregistered later phase;
- final training phase evaluates whether recovered behavior survives reduced recovery emphasis;
- all sample counts and ordering seeds are materialized into a manifest and hashed.

Arm A receives the same number of additional example presentations as Arm B, but through ordinary append/balanced sampling without recovery priority.

## Retention / eviction connection (#35)

The recovery buffer is an active-state training mechanism, not permanent dataset inflation.

Every recovery item records:

- source family;
- failure class;
- activation reason;
- initial weight;
- decay phase;
- retirement eligibility.

A recovery item becomes lower priority only after the preregistered evaluation condition is met; it is never silently deleted from provenance.

## Closed-loop connection (#36)

Stage C does not perform uncontrolled online learning. Instead it models closed-loop adaptation through deterministic offline receipts:

`decision -> observed eval failure -> recovery classification -> next fixed curriculum -> reevaluation`.

This preserves reproducibility while testing the co-adaptation/recovery principle inspired by neuroprosthetic and robotic control systems.

## Acceptance criteria

Arm B is considered a successful applicability-recovery candidate only if all conditions hold on both replicas:

1. heldout negative `NO_CALL` is substantially restored from the Stage B tuned reference of 0/24; preregistered minimum: >= 20/24;
2. positive heldout correct count is >= 32/72, preserving the Stage B tuned reference floor;
3. dominant semantic decision share is <= 0.70;
4. observable output does not collapse into a single applicability class;
5. recovery remains after the curriculum enters its reduced-weight phase;
6. Arm B outperforms Arm A on heldout negative NO_CALL without worse positive-heldout correctness;
7. storage/eval/runtime failure is never interpreted as NO_CALL success.

If criterion 1 fails, disposition is `REJECTED_APPLICABILITY_RECOVERY_FAILED`.
If criterion 2 fails after criterion 1 passes, disposition is `REJECTED_POSITIVE_RETENTION_REGRESSION`.
If collapse criterion fails, disposition is `REJECTED_DECISION_COLLAPSE`.
If Arm B does not beat Arm A under the paired criteria, disposition is `INCONCLUSIVE_RECOVERY_SPECIFICITY`.
Only two-replica success yields `ACCEPTED_STAGE_C_APPLICABILITY_RECOVERY`.

## Measurements

Each arm/replica receipt records at minimum:

- positive correct / total for train and heldout;
- negative NO_CALL / total for train and heldout;
- PROBE/READY/UNKNOWN/NO_CALL distribution;
- dominant semantic decision rate;
- applicability-class distribution;
- canonical-state field accuracy/confusion;
- recovery-phase metrics before and after weight decay;
- exact dataset/curriculum/seed/config hashes;
- exact base checkpoint and produced artifact hashes.

## Repository layout

New Stage C files live beside, not inside, the frozen Stage B dataset:

```text
experiments/needle-stage-c-applicability/
  contract/
  source/
  data/
  manifests/
  results/          # generated/runtime only, not authority unless committed intentionally
scripts/
  build_stage_c_applicability_dataset.py
  validate_stage_c_applicability_dataset.py
  run_stage_c_train.sh
  run_stage_c_eval.sh
  stage_c_quality_receipt.py
tests/
  test_stage_c_applicability_dataset.py
  test_stage_c_applicability_quality.py
  test_stage_c_applicability_contract.py
```

Stage C may call existing Stage B evaluator/helpers where byte-level behavior is intentionally reused; duplication should be avoided unless isolation is required for scientific provenance.

## Execution boundaries

- no production infrastructure work;
- no Vercel/Cloudflare dependency;
- no hidden teacher/model-generated labels;
- no heldout leakage;
- no free-form reasoning targets;
- no change to Stage B published artifacts or disposition;
- training remains manually dispatched and exact-SHA gated;
- two replicas remain independent;
- receipts remain the acceptance authority.

## First implementation milestone

Before any full training run, Stage C must prove locally that:

1. Arm A and Arm B have identical total presentation budgets;
2. heldout families/queries are absent from training projections;
3. canonical state is enum-valid and deterministic;
4. recovery weighting and decay are materialized and byte-stable;
5. Stage B frozen behavioral evaluator still classifies the same reference fixtures identically;
6. all unit/contract tests pass.

## Council refinement: factorized applicability and canonical recovery state

The approved Stage C design is refined to make tool applicability a first-class gate rather than a flat four-way decision.

### Factorized decision model

Stage C MUST evaluate applicability in two stages:

```text
input -> applicability gate
          |- NONE  -> NO_CALL
          `- ROUTE -> semantic decision: PROBE | READY | UNKNOWN
```

The primary recovery objective targets the first gate because Stage B's dominant failure was loss of NO_CALL discrimination. The semantic decision head remains separately measured and must not be allowed to hide applicability collapse.

### Canonical state is structured, not free-form rationale

The canonical target/state uses bounded enum fields only. It MUST NOT contain free-form rationale or chain-of-thought-like explanatory text. A minimal decision record is:

```json
{
  "applicability": "NONE|ROUTE",
  "decision": "NO_CALL|PROBE|READY|UNKNOWN",
  "tool_need": "unnecessary|required|helpful|unknown",
  "evidence_state": "sufficient|insufficient|conflicting",
  "cost_class": "low|medium|high",
  "risk_class": "low|medium|high"
}
```

`decision=NO_CALL` is valid only when `applicability=NONE`; otherwise `decision` MUST be one of `PROBE|READY|UNKNOWN`.

### Canonical recovery state

Recovery bookkeeping is stored as JSON state and training JSONL is a deterministic projection from that state. At minimum each recovery entry records:

```json
{
  "case_id": "...",
  "class": "negative_boundary",
  "failure_count": 0,
  "success_streak": 0,
  "recovery_priority": 0.0,
  "last_outcome": "FALSE_CALL|CORRECT_NO_CALL|OTHER",
  "retention_zone": "recent|active|normal",
  "evictable": true
}
```

Priority increases after false CALL outcomes and decays only after preregistered stable success. Heldout cases MUST never enter the recovery state.

### Arm parity

Arm A and Arm B MUST use the same base checkpoint, positive training examples, heldout set, training budget, evaluation harness, and seeds. Arm B may differ only in preregistered recovery-state-driven sampling and the canonical factorized target representation.
