# Needle 3 deployment-equivalence canary

Issue: #65
Research parent: #61
Fault taxonomy consumer: #66

## Scope

This is a small current-release canary for one question:

> Does selective tool-calling behavior survive the path from base reference
> execution through local LoRA adaptation and into the exported/deployed
> `.cact` surface?

It is not a general Needle 3 quality benchmark and it is not Stage C retraining.

The execution snapshot is pinned by
`experiments/needle3-deployment-canary/v1/manifest.json`:

- released package: `cactus-needle==3.0.4`;
- source parent: `f189b23ebf34b98bcc8f9ee819249425c6623a32`;
- release tag commit: `49f6759ae70ac24c479baf70f966fc9c787bf9ac`;
- exact PyPI wheel filename and SHA-256;
- frozen 12-case heldout canary;
- frozen 48-row balanced training fixture.

The live upstream repository may move after this snapshot. That is currentness
information, not permission to silently change the execution target. A new
release/source target needs a new narrow issue or an explicit #65 revision.

During the 2026-09-23 currentness audit, upstream CLI-help drift around
`finetune --layers` was reported as `cactus-compute/needle#139`. That report
is useful reciprocal upstream feedback but is not scientific evidence for this
canary.

## Three surfaces

The same frozen cases are evaluated on:

1. `base_reference`: JAX checkpoint reference;
2. `lora_reference`: the same checkpoint with the exact local LoRA merged in
   JAX;
3. `built_cact`: the exact exported `.cact` through the deployed Needle 3
   engine.

Surface provenance binds the exact base checkpoint, LoRA adapter, built archive,
runtime engine, package wheel, and fixture.

A run is `INCONCLUSIVE` if the LoRA changes none of the frozen canary
predictions. This prevents a vacuous base == LoRA == built result from becoming
`NO_CURRENT_SIGNAL`.

Correctness, route-call reachability, negative `NO_CALL`, false calls,
decision concentration, pairwise deployment mismatches, and latency are kept as
separate measurements.

## Manual workflow

`.github/workflows/needle3-deployment-canary.yml` is intentionally
`workflow_dispatch` only. It accepts an exact 40-hex `experiment_sha`,
checks out that revision, verifies the checkout, and records the workflow
launcher SHA separately.

The repository QA gate runs before the expensive environment setup.

Heavy stages run through
`scripts/run_needle3_canary_stage.sh`, which composes:

- `scripts/execution_telemetry.py` for terminal execution/checkpoint/artifact
  evidence;
- `scripts/needle3_stage_diagnostics.py` for periodic elapsed-time,
  available-memory, root-disk, tracked-path-size, and child max-RSS evidence.

The workflow separates setup, checkpoint download, engine resolution, base
reference, training, LoRA reference, build, built execution, provenance, and
aggregation. Evidence upload is `if: always()` and keyed by both GitHub run ID
and run attempt.

A second job downloads the exact run-attempt artifact, validates stage
checkpoints against uploaded artifacts, and rebuilds the scientific receipt from
the downloaded surface results and provenance.

Missing built artifacts consume the promoted #66 fault taxonomy and stay
`BLOCKED`; absence never becomes `NO_CALL` or a scientific outcome.

## Diagnosing an Actions failure

Read evidence in causal order:

1. failing stage `_evidence/telemetry/<stage>/checkpoint.json`;
2. `heartbeat.jsonl` for terminal/progress state;
3. `_evidence/diagnostics/<stage>.json` for elapsed time, memory, disk, and
   tracked-size extrema;
4. typed fault receipts under `_evidence/faults/`, when present;
5. only then the surrounding Actions log.

A green workflow is not a scientific verdict. The receipt remains a bounded
model/domain witness until the normal acceptance gate.

## Codespace reproduction boundary

Use a Codespace only when a hosted run gives a concrete failing stage or
environment hypothesis. Check out the exact failing `experiment_sha` and run
the same fixed command from the workflow.

Do not reuse the GitHub run identity for interactive reproduction. Give the
Codespace run a distinct telemetry identity, for example:

```sh
export EXPERIMENT_SHA=<exact failing sha>
export LAUNCHER_SHA=<launcher sha from the hosted run>
export GITHUB_RUN_ID=codespace-repro
export GITHUB_RUN_ATTEMPT=1
```

Codespace success or failure proves only that Codespace runtime. It can explain
or reproduce a hosted failure, but it does not replace hosted readback or
scientific acceptance.
