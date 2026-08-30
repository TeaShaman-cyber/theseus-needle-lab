# Architecture

Theseus Needle Lab separates research intent, execution evidence, provenance, and human-readable views.

```text
Issue
  -> commit / PR
  -> GitHub Action
  -> artifact + SHA-256
  -> evaluation
  -> verification receipt
  -> ACCEPTED | REJECTED | INCONCLUSIVE
```

## Authority boundaries

- Repository history is the versioned source for code, workflow definitions, schemas, and canonical documentation.
- Issues record research intent, questions, criteria, and dispositions.
- GitHub Actions provide execution evidence only for their declared jobs.
- Receipts provide machine-readable provenance and verification state.
- GitHub Wiki and Pages are navigation/presentation layers, not authority over versioned repository records.
- GitHub-hosted artifacts are retention-bound storage; integrity is established by recorded content hashes, not by assuming storage immutability.

Issue #1 established the executable Needle interface well enough to add one bounded CPU feasibility smoke. The smoke is execution evidence only; broader training infrastructure still requires measured runtime evidence and separate review.
