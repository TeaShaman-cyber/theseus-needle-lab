# Deterministic max-len A/B — Issue #8

Question: does removing target truncation improve the bounded 12-row Needle 2 microlearning task when every other controllable factor is held fixed?

The branch inherits the verified evaluator and public dataset lineage from Issue #4. Both arms use the same explicit NumPy seed before delegating to pinned `cactus-needle 2.0.8` fine-tuning, the same one-epoch optimizer/LoRA settings, uniform W4 export, and the same 256-token inference budget.

```text
A: max_len cap 128
B: max_len cap 1024 (upstream default cap; Needle chooses the effective bucket)
```

A pre-training target-coverage report is mandatory. Arm B must have zero truncated training targets or the workflow stops before fine-tuning.

The primary measurement is exact 12-row train replay. The existing 24-row held-out evaluation is secondary until the model can express the training task.
