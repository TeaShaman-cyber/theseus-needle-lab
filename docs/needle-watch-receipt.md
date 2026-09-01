# Needle Watch receipt v0.1

The Needle Watch collector is a deterministic public-source sensor for the A/B/C discovery experiment in Issue #21. It does not decide whether a candidate is scientifically important.

## Canonical paths

```text
data/latest/needle-watch.json
data/YYYY-MM-DD/needle-watch.json
```

One run writes identical bytes to both paths. `latest` is a convenience pointer; dated files are the replay surface.

## Top-level fields

- `schema_version`: currently `needle-watch-receipt-v0.1`.
- `run_id`: GitHub Actions run identity or deterministic local fixture identity.
- `generated_at`, `window_start`, `window_end`: UTC RFC3339 timestamps.
- `collector_revision`: source Git commit used by the collector.
- `source_health[]`: operational evidence for each configured source/query family.
- `candidates[]`: normalized discovery candidates with deterministic IDs.

## Null-day rule

A receipt with no candidates is a genuine null day only when every source-health record is `ok`. An empty candidate list accompanied by `partial` or `failed` source health is not evidence that nothing changed.

```text
candidates = [] + all sources ok     -> valid null day
candidates = [] + source failed      -> collection failure state
```

The test fixtures `tests/fixtures/null-day-source.json` and `tests/fixtures/source-failure.json` preserve this distinction as an executable activation gate.

## Candidate boundary

The collector records enough identity for a later task to re-fetch and verify the primary source: canonical URL, source identity, discovery route, watch-line matches, observation time, publication/push time, and a content fingerprint. It does not assign FACT/INFERENCE/HYPOTHESIS or a Notion promotion state.

## Task routing

During the shadow experiment, ChatGPT Tasks may use the native GitHub app as a read-only sensor for these public receipts and referenced public GitHub evidence. Native GitHub mutations are prohibited by experiment policy. MarcoPolo remains the engineering/write route for repository changes and verified read-back.
