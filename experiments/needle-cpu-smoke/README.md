# Needle CPU smoke

Issue: #1 — map the real Needle learning interface and runtime requirements.

Question: can a standard public GitHub-hosted `ubuntu-latest` runner complete a real Needle 2 `finetune -> build` path on the public base checkpoint within a bounded CPU-only job?

This is a feasibility measurement, not a model-quality claim.

Pinned experiment shape:

- package: `cactus-needle[train]==2.0.8`
- upstream source reference: `cactus-compute/needle@ee221ce7c13579d9809209b979a9b7a50936614c`
- 12 hand-written public examples
- `max_len=128`
- `epochs=1`
- `batch_size=2`
- LoRA rank `4`
- no generated examples
- no OpenRouter
- no secrets
- GitHub job timeout: 45 minutes

Measured outputs include dependency-install time, checkpoint-download time, fine-tune wall time and peak RSS, adapter size/hash, build wall time and peak RSS, `.cact` size/hash, runner/image identity, package versions, and a machine-readable receipt.
