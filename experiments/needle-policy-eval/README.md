# Needle policy evaluation

Issue: #4 — compare the untouched base Needle 2 model with the exact tuned artifact produced by CPU smoke run `33319821037`.

This experiment asks only whether the tiny 12-example LoRA changed behavior on a bounded held-out set in the intended epistemic-routing direction.

## Fixed tuned artifact

```text
run: 33319821037
artifact: needle-cpu-smoke-33319821037
tuned.cact sha256: 3c0c684888c0d796e1b3a62326fbb1f3cc991f6ee5a0e596ac448df99edef10a
```

The adapter is not retrained for this comparison.

## Held-out set

24 hand-written cases, none copied from the 12 smoke-training queries:

- 6 paraphrases of project epistemic rules;
- 6 cases using previously unseen harness/provider names;
- 6 verification/currentness boundary cases;
- 6 unrelated negative controls where `route` should not be called.

Expected labels are balanced: 6 each of `PROBE`, `READY`, `UNKNOWN`, and `NO_CALL`.

## Scoring

The single available tool is the same constrained `route(decision)` schema used during the smoke training corpus. The observed model envelope is reduced to:

```text
PROBE | READY | UNKNOWN | NO_CALL | INVALID
```

`confidence` is recorded but never used for scoring or acceptance. Tuned Needle weights intentionally report `confidence=None` because LoRA does not update the confidence head.

Inference uses `max_new_tokens=256`, matching the pinned upstream Needle API default; the value is explicit in the workflow and recorded in evaluation receipts.

Base and tuned models run in separate processes because Needle's native engine keeps tuned-weight binding process-global.

A successful workflow means the comparison executed and produced auditable results. It does not require the tuned model to outperform base.
