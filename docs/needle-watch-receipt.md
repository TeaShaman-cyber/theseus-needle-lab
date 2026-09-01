# Needle Watch receipt v0.2

The Needle Watch collector is a deterministic public-source sensor for the A/B/C discovery experiment in Issue #21. It discovers candidates and records collection evidence; it does not decide scientific importance.

## Canonical paths

```text
data/runs/<run_id>.json       # immutable replay record for one collector run
data/daily/YYYY-MM-DD.json    # convenience pointer to the latest run observed that UTC day
data/latest/needle-watch.json # convenience pointer to the latest published run
```

All three files emitted by one run are byte-identical. A per-run file must never be replaced by different bytes. `daily` and `latest` are mutable views; `runs` is the replay surface.

The legacy v0.1 path `data/YYYY-MM-DD/needle-watch.json` remains historical data and is not the v0.2 replay contract.

## Top-level fields

- `schema_version`: `needle-watch-receipt-v0.2`.
- `run_id`: immutable execution identity. In GitHub Actions this is `<github.run_id>-attempt-<github.run_attempt>` because `run_id` alone is reused across reruns; local fallback IDs include the UTC timestamp.
- `generated_at`, `window_start`, `window_end`: UTC RFC3339 timestamps.
- `collector_revision`: source Git commit used by the collector.
- `source_health[]`: operational and coverage evidence for each configured source/query family.
- `candidates[]`: normalized discovery observations with stable entity and immutable revision identity.

## Source-health and coverage semantics

For GitHub repository search, every source-health record includes:

- `records_seen`: result records returned by the search response;
- `total_count`: GitHub's reported match count, or `null` when the source request failed;
- `returned_count`: records returned in this response;
- `incomplete_results`: GitHub's own incomplete-search flag, or `null` on transport failure;
- `truncated`: whether `total_count` exceeds the returned result set, or `null` on transport failure;
- `cursor_or_watermark`: the exact second-precision `window_start` used in `pushed:>=...` discovery;
- `status`: `ok`, `partial`, or `failed`;
- `error_class`: compact reason when collection is partial or failed.

`ok` therefore means both transport success and complete coverage within the configured result bound. A capped or provider-declared incomplete search is `partial`, not `ok`.

## Null-day rule

A receipt with no candidates is a genuine null day only when every source-health record is `ok`.

```text
candidates = [] + all sources ok        -> valid null day
candidates = [] + partial/failed source -> not evidence of no change
```

The fixtures `tests/fixtures/null-day-source.json` and `tests/fixtures/source-failure.json` preserve this distinction as an executable activation gate.

## Candidate identity

A GitHub candidate separates project identity from observation identity:

- `source_entity_id`: stable provider entity, currently `github-repo:<repository_id>`;
- `source_identity`: human-readable repository/default-branch identity;
- `upstream_revision`: immutable observed default-branch commit SHA;
- `content_fingerprint`: revision fingerprint (`commit:<sha>`);
- `candidate_id`: deterministic hash of source class, canonical URL, source identity, and content fingerprint;
- `seen_in_previous_snapshot`: the exact candidate observation existed in the previous `latest` snapshot;
- `entity_seen_in_previous_snapshot`: the same stable repository entity existed in the previous snapshot, even if its revision changed.

These are previous-snapshot relations, not claims that the repository has or has not ever appeared in all historical receipts.

If one repository disappears or its default branch cannot be resolved between search and revision lookup, other usable candidates are retained and the source becomes `partial` with `RevisionResolutionFailed`.

## Task freshness gate

A/B/C tasks must not equate a structurally valid `latest` receipt with the current experiment cycle. Receipt consumers should require the expected schema and a fresh `generated_at` for the current local day/cycle before using it as Arm B/C input. A stale receipt is an operational failure for that cycle, not a null day.

## Task routing

During the shadow experiment, ChatGPT Tasks may use the native GitHub app as a read-only sensor for these public receipts and referenced public GitHub evidence. Native GitHub mutations are prohibited by experiment policy. MarcoPolo remains the engineering/write route for repository changes and verified read-back.
