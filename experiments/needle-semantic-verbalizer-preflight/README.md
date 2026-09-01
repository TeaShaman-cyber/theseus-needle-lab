# Needle semantic verbalizer preflight

Issue: #26

This zero-training Stage A preflight compares three semantic verbalizer interfaces under the exact accepted corrected Needle framing and schema serialization inherited from #16/#18:

- `PROBE / READY / UNKNOWN`;
- `probe / ready / unknown`;
- `check / ready / unknown`.

The purpose is to choose a less pathological **interface prior** before a realistic supervised-adaptation run. A zero-shot winner is **not evidence of learned policy**. The experiment reports applicability, mapped accuracy, class skew/collapse, exact prediction vectors, serialized prompt/schema contracts, and label tokenization.

No fine-tuning or weight export occurs in this stage.
