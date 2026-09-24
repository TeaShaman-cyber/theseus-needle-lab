# Typed decision benchmark v1

Lifecycle owner: issue #56.

This directory implements the preregistered public/synthetic routing comparison. The primary fixture has visible labels and is not blinded held-out evidence. The legacy fixture is continuity-only and is never pooled into one headline score.

The included v1 execution matrix is constant-UNKNOWN baseline, Needle 3 base, SemIf Qwen3-0.6B Q8, and Kev-0.8B. NanoJev, Jev/System One, Nimble, and tuned Needle remain explicitly excluded or deferred according to issue #56.

Repository QA validates identities, normalization, scoring, workflow contracts, and receipts. QA must not execute candidate models and is not benchmark evidence.

Provider adapters must never expose the expected class to inference. SemIf receives only state/question/options. Kev requires a label field in its encoder record; v1 uses constant dummy label 0 for every question, and this field is not the benchmark target. Kev logits/probabilities are produced from encoded tokens; the dummy label is retained only as encoder metadata.

All result rows bind the exact input query hash, request/response hashes, adapter identity, runtime identity, and model identity. Candidates not marked BENCHMARK_READY cannot be scored.

An exact probability tie fails closed to ERROR rather than introducing an arbitrary class tie-break.
