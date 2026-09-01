# Needle Watch receipt data

This directory contains machine-readable public discovery receipts produced by the Needle Watch collector.

- `latest/needle-watch.json` is the convenience pointer consumed by read-only tools.
- `YYYY-MM-DD/needle-watch.json` is the dated replay snapshot.
- The two files emitted by one run must be byte-identical.
- Receipts contain discovery candidates and source-health evidence, not scientific conclusions.
- `candidates: []` counts as a valid null result only when source-health records show successful collection.

The authoritative receipt contract and experiment state are tracked in GitHub Issue #21.
