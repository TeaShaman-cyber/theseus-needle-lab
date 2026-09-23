# Needle 3 multi-provider corpus inventory - Issue #26

This is the current-Needle-3 successor preflight for Issue #26.

It does not revive the historical Needle 2.0.8 Stage B branch or overwrite its
REJECTED_APPLICABILITY_REGRESSION result. The old 360-train / 96-heldout
synthetic experiment remains historical evidence.

This preflight inventories private historical interaction corpora without
committing raw conversation text. Its purpose is to establish whether a larger,
provider-diverse, observable-episode pool exists before any new SFT projection
or training is authorized.

Source selection deliberately avoids double counting:

- ChatGPT: bound Session Search corpus filtered to chatgpt-export;
- DeepSeek: standalone DeepSeek corpus-v1 filtered to deepseek-export;
- xAI/Grok: standalone xAI corpus-v1 filtered to xai-export.

The extractor records exact SQLite hashes/sizes, schema identity, coverage,
message-shape counts, branch overlap, canonical-message duplication, observable
user-turn episode counts, and cross-provider hash overlap.

It does not infer PROBE, READY, UNKNOWN, or NO_CALL from historical provider
behavior. Absence of a tool evidence row is not proof that a tool should not
have been called.

Raw corpora are private historical evidence. The committed inventory is
metadata-only. Projected examples require separate privacy/publicability
review, semantic-family adjudication, label adjudication, and leakage checks.

## Inventory v1 observed on 2026-09-23

Exact metadata inventory:

- ChatGPT export slice: 303 sessions, 139,293 selected messages, 29,084 eligible user-turn episodes;
- DeepSeek export: 43 sessions, 64,662 selected messages, 28,044 eligible user-turn episodes;
- xAI/Grok export: 59 selected sessions, 17,790 selected messages, 6,018 eligible user-turn episodes;
- total pre-adjudication episode pool: 63,146.

The pure ChatGPT and xAI export adapters expose no tool-role evidence rows in this
corpus schema. DeepSeek exposes 259 tool evidence messages and 201 user-turn
episodes containing observed tool evidence. This is an observability property,
not a behavioral conclusion: no-tool labels remain NOT_ADJUDICATED.

Cross-source exact episode-signature overlap is zero in this inventory.
Canonical-message hashes have small cross-source overlap, so later projection
must still deduplicate and screen semantic near-duplicates.

The current Needle 3 deployment-canary heldout file is SHA-bound in inventory.json
and must remain excluded from training. Historical Stage B heldout families also
remain conceptually excluded even though that closed branch is not copied into
this current-main successor.
