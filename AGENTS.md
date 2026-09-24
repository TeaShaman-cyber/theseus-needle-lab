# Repository Agent Contract

This file is the repository-local operating contract for agentic workers in Theseus Needle Lab.

It is an executable projection of the existing repository methodology. It does not replace or outrank the canonical research documents.

Canonical sources:
- README.md — research boundary and top-level research flow.
- docs/architecture.md — authority boundaries and evidence separation.
- docs/experiment-lifecycle.md — lifecycle states, acceptance, degraded evidence, outcomes, and dispositions.
- docs/cookbook/README.md — accepted operational/scientific rules.

If this file conflicts with one of those sources on the same concern, stop with BLOCKED, record the conflict in a covering Issue, and resolve it through a reviewed repository change. Do not invent precedence.

## Mandatory preflight

Before changing experiment code, creating experiment infrastructure, or running an experiment:

1. Verify the current authoritative repository revision relevant to the work.
2. Identify the covering GitHub Issue.
3. Identify the experiment lifecycle state in that Issue.
4. Confirm that the prerequisites for that lifecycle state are recorded.
5. Discover the existing repository QA/acceptance routes before adding a new verifier.
6. Identify the authority boundary for any mutation, promotion, release, or externally consequential action.

If no covering Issue exists for new research work, create one before proceeding.

## SPECIFIED is required before experiment implementation

An experiment must not advance beyond specification until its Issue records:
- the research question or hypothesis;
- the data / fixture / manifest identity;
- the configuration identity;
- success criteria;
- failure or falsifier criteria;
- privacy classification.

If any required item is missing, the allowed next action is to improve the specification. Do not build or run the experiment first and backfill the methodology later.

## PLANNED is required before execution

Before execution, the Issue must additionally record:
- the execution route;
- expected artifacts and receipts;
- the deterministic QA route;
- the recovery / checkpoint boundary;
- the verification plan.

Execution begins only against an exact planned source/configuration identity. A branch name, workflow name, provider label, or nominal artifact name is not a substitute for realized identity.

## Lifecycle boundaries are strict

Use the repository lifecycle as written:

SPECIFIED -> PLANNED -> WORKING -> QA -> EXECUTING -> ARTIFACT_PROVENANCE -> MODEL_OR_DOMAIN_WITNESS -> REVIEW -> ACCEPTANCE_GATE -> PROMOTION -> READBACK -> DISPOSITION

Not every line must reach promotion. Work may terminate earlier with an explicit disposition when blocked, parked, superseded, abandoned, rejected, or inconclusive.

### QA

tools/dev/check and hosted repository checks establish deterministic repository QA for the exact revision they test.

QA does not prove model quality, scientific truth, generalization, provider availability beyond the checked route, or scientific acceptance.

Do not convert a green workflow into a model/domain claim.

### Execution and artifact provenance

Execution evidence proves only the declared execution postconditions.

Important execution and artifact evidence must bind the realized state, including relevant exact source revision, configuration, data/fixture identity, seeds where applicable, artifact hashes, runtime identity, and recovery provenance.

A downstream failure does not erase a completed upstream stage.

### Model or domain witness

A model/domain witness is bounded evidence for the exact evaluated artifact, configuration, and population.

Do not generalize a bounded witness to other revisions, runtimes, datasets, providers, or populations without separate evidence.

### Review

Review findings are evidence, not authority.

For each finding:
- check applicability to the current exact revision;
- distinguish blocking findings from follow-up work;
- do not expand the active scope merely to chase an unrelated reviewer suggestion;
- route valid out-of-scope findings to a durable Issue instead of silently absorbing them;
- do not treat a stale finding as current after the relevant fix has been verified.

Unresolved in-scope blocking findings stop acceptance or promotion.

### Acceptance gate

Scientific acceptance is explicit.

The available QA, execution, provenance, model/domain witness, and review evidence must be considered at an explicit acceptance gate for the declared purpose.

A workflow, receipt field, model output, reviewer comment, or agent assertion cannot silently substitute for the acceptance gate.

## Separate research outcome from delivery disposition

Research outcome is one of:

ACCEPTED | REJECTED | INCONCLUSIVE

Delivery / branch disposition is a separate axis, for example:

PROMOTED | PARKED | SUPERSEDED | ABANDONED | BLOCKED

Do not rewrite a negative or inconclusive scientific result merely because its branch merged, failed to merge, or was parked.

## Promotion and readback

Promotion is a consequential mutation separate from scientific acceptance.

Promotion requires current authority for the intended target. Important promotion requires authoritative readback of the promoted target and exact identity.

Executor self-report is insufficient when independent readback is available.

Do not claim PROMOTED after failed, partial, unavailable, or mismatched readback. Preserve the observed state as BLOCKED, UNKNOWN, or REPROBE_REQUIRED as appropriate.

## Degraded and external evidence

Use the repository evidence states without inflation:
- DEGRADED — required evidence is partial or lower quality than declared;
- BLOCKED — a required stage could not execute or verify;
- UNKNOWN — available evidence is insufficient;
- STALE — evidence was valid for an earlier revision/runtime only;
- REPROBE_REQUIRED — the smallest authoritative current-state check must be repeated before reliance.

Provider outages, unavailable reviewers, missing artifacts, and incomplete telemetry must never be converted into PASS or absence-of-effect claims.

If degraded evidence is accepted as non-blocking for a bounded purpose, record that exception explicitly at the acceptance gate.

## Privacy and public-repository boundary

Never commit or emit to public logs:
- secrets or credentials;
- private corpora;
- private conversation content;
- other sensitive user data not explicitly authorized for public release.

Synthetic/public fixtures must not silently incorporate private conversation material.

## Operational discipline

- Prefer the repository's existing deterministic verifier before writing a new one.
- Make the smallest change that advances the declared lifecycle state.
- Preserve negative and inconclusive evidence.
- Keep implementation evidence, scientific evidence, review evidence, acceptance, and promotion distinct.
- Record durable state in Issues, commits, receipts, and reviewed repository documents rather than relying on chat-local promises.
- If current evidence is insufficient for the next claim, stop at the correct evidence state instead of guessing.

## Benchmark-specific consequence

For comparative benchmark work such as Issue #56:
- do not execute candidates until the benchmark Issue is both SPECIFIED and PLANNED under this contract;
- preregister the population/fixture identity, candidate/configuration identity, hypothesis or research question, falsifier/success criteria, privacy classification, run matrix, receipt/artifact plan, QA route, recovery boundary, and verification plan before execution;
- deterministic harness QA is not benchmark evidence;
- runtime feasibility is not model-quality evidence;
- model-quality results remain bounded witnesses until review and explicit acceptance.
