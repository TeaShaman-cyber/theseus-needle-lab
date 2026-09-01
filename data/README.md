# Needle Watch receipt data

This directory contains machine-readable public discovery receipts produced by the Needle Watch collector.

v0.2 layout:

- `runs/<run_id>.json` — immutable per-run replay record;
- `daily/YYYY-MM-DD.json` — latest receipt for that UTC day;
- `latest/needle-watch.json` — latest published receipt consumed by read-only tools.

The three files emitted by one run are byte-identical. `daily` and `latest` are convenience views; only `runs` is the immutable replay surface.

The older `YYYY-MM-DD/needle-watch.json` layout is retained as v0.1 historical data.

Receipts contain discovery candidates plus source-health/coverage evidence, not scientific conclusions. `candidates: []` counts as a valid null result only when all source-health records are `ok` and coverage is complete.

The authoritative receipt contract and experiment state are tracked in GitHub Issue #21.
