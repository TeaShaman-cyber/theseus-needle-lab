# Architecture

Theseus Needle Lab separates research intent, deterministic QA, execution
evidence, model/domain evidence, review, acceptance, promotion, and readback.

```text
Issue / specification
  -> commit / PR
  -> deterministic QA
  -> execution / running
  -> artifact + provenance
  -> model/domain witness
  -> review
  -> explicit acceptance gate
      |-- accepted + authorized --> promotion -> authoritative readback
      \-- no promotion / blocked / parked --------------------------|
  -> terminal disposition
```

The research outcome (`ACCEPTED | REJECTED | INCONCLUSIVE`) is recorded
separately from delivery/branch disposition.

## Authority boundaries

- Repository history is the versioned source for code, workflow definitions,
  schemas, and canonical documentation.
- Issues record research intent, questions, criteria, evidence, and
  dispositions. An Issue is a coordination/evidence container, not execution,
  merge, release, or acceptance authority.
- GitHub Projects, Wiki, and Pages are navigation/coordination views, not
  authority over versioned repository records.
- GitHub Actions provide execution evidence only for their declared jobs.
  Workflow success is not scientific acceptance.
- The canonical `tools/dev/check` endpoint provides deterministic repository QA
  only; its PASS is not model/domain evidence.
- Receipts provide machine-readable provenance and verification state, but a
  receipt field cannot self-authorize acceptance or promotion.
- Model/domain witnesses are bounded by the exact evaluated artifact,
  configuration, and population. They do not silently generalize beyond that
  boundary.
- Review records findings; it does not itself grant merge/promotion authority.
- Acceptance is an explicit gate over QA, execution/witness provenance, and
  review evidence for a declared purpose.
- Work that is blocked, parked, superseded, abandoned, or declined at acceptance
  can move directly to terminal disposition without pretending promotion occurred.
- Promotion is a separate consequential mutation and requires current authority.
- Important promotion requires readback from the authoritative target.
- GitHub-hosted artifacts are retention-bound storage; integrity is established
  by recorded content hashes, not by assuming storage immutability.

## Runtime and recovery boundaries

Expensive training/evaluation stages should preserve recoverable outputs before
riskier downstream stages when losing the completed work would materially
increase recovery cost. A downstream failure must not retroactively erase the
evidence that an upstream stage completed.

Telemetry and observability are QA surfaces when they are required to classify
known failure modes, but they must remain lightweight relative to the workload.
Missing or degraded telemetry changes what can be claimed about a failure; it
does not justify inventing a cause.

See [experiment lifecycle](experiment-lifecycle.md) for the process states,
degraded evidence states, research outcomes, and terminal dispositions.
