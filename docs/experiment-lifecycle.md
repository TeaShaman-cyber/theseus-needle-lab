# Experiment lifecycle

```text
IDEA
  -> SPECIFIED
  -> RUNNING
  -> VERIFYING
  -> ACCEPTED | REJECTED | INCONCLUSIVE
```

An experiment starts as an Issue. Before execution it records the question or hypothesis, data/manifest identity, configuration identity, success/failure criteria, and privacy classification. Commits and PRs reference that Issue. Execution links back to the exact source revision. Evaluation and verification are recorded separately from execution success.

`REJECTED` and `INCONCLUSIVE` are preserved outcomes, not failures of record keeping.
