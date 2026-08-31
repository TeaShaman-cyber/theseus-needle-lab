# Needle target representation × training strength 2×2

Issue: #10.

This bounded experiment follows the negative max-length result in #8. It asks whether the tiny routing task is limited primarily by optimization strength, by supervision-target representation, or by an interaction between them.

| Arm | Training target | Epochs |
|---|---|---:|
| A | reasoning + tool-call | 1 |
| B | reasoning + tool-call | 3 |
| C | tool-call only | 1 |
| D | tool-call only | 3 |

Fixed controls: exact Needle 2 checkpoint, `cactus-needle==2.0.8`, NumPy shuffle seed 0, default validation split, batch 2, LR `1e-4`, LoRA rank 4 / alpha 32, max-len cap 1024, uniform W4 export, and 256-token evaluation budget.

The tool-call-only dataset is derived deterministically by removing only the `reasoning` field. It is a cheap target-representation probe, not equivalent to SWE-Prime segment-level loss masking.

Primary endpoint: training-set replay. Secondary endpoint: the existing 24-row held-out policy set.
