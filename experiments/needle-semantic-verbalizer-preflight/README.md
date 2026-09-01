# Needle semantic verbalizer preflight

Issue: #26

This zero-training Stage A preflight compares three semantic verbalizer interfaces under the exact accepted corrected Needle framing and schema serialization inherited from #16/#18:

- `PROBE / READY / UNKNOWN`;
- `probe / ready / unknown`;
- `check / ready / unknown`.

The purpose is to choose a less pathological **interface prior** before a realistic supervised-adaptation run. A zero-shot winner is **not evidence of learned policy**. The experiment reports applicability, mapped accuracy, class skew/collapse, exact prediction vectors, serialized prompt/schema contracts, and label tokenization.

No fine-tuning or weight export occurs in this stage.

## Verified Stage A result

Exact experiment source: `1435f3edd38ef0f4e9d066935be75a0100091eb3`, workflow run `33557711455`, attempts 1 and 2.

Both attempts reproduced every per-case prediction exactly for all three arms (12/12 each), with identical tokenizer and prompt-contract evidence.

| Arm | Valid calls | Correct | Dominant semantic prediction | Collapse |
|---|---:|---:|---|---|
| `PROBE / READY / UNKNOWN` | 10/12 | 3/12 | `UNKNOWN` 0.600 | no |
| `probe / ready / unknown` | 9/12 | 5/12 | `PROBE` 0.778 | yes |
| `check / ready / unknown` | 5/12 | 3/12 | `PROBE` 0.800 | yes |

The predeclared stop rule rejects `check / ready / unknown`: it materially reduces route applicability and collapses toward `PROBE`. Lowercase also crosses the collapse threshold despite higher raw accuracy. Stage B therefore keeps the uppercase semantic reference as the least-pathological observed interface prior. This is not evidence that uppercase labels are optimal after supervised training.

See `receipt.public.json` for the sanitized machine-readable result and exact attempt receipt hashes.
