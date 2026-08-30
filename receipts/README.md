# Receipts

Receipts are machine-readable provenance records for executed experiments. The initial schema is intentionally not frozen until Issue `Define experiment receipt schema v0.1` is resolved.

Candidate fields include source commit SHA, workflow identity, data/config hashes, random seed, runner/image identity, tool versions, artifact hash and storage/retention class, evaluation metrics, and verification status.

GitHub Artifacts are retention-bound storage. A recorded SHA-256 identifies content for integrity verification; it does not make the storage immutable.
