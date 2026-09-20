# Experiment lifecycle

Theseus Needle Lab tracks **process state** separately from the **research outcome**.
Historical receipts that used the original lifecycle remain valid; this contract adds
boundaries for new work and does not rewrite past evidence.

## Process lifecycle

```text
IDEA
  -> SPECIFIED
  -> PLANNED
  -> WORKING
  -> QA
  -> EXECUTING
  -> MODEL_OR_DOMAIN_WITNESS
  -> REVIEW
  -> ACCEPTANCE_GATE
     |-- accepted + promotion authorized --> PROMOTION -> READBACK -> DISPOSITION
     \-- no promotion / blocked / parked --> DISPOSITION
```

An experiment starts as an Issue. Before execution it records the question or
hypothesis, data/manifest identity, configuration identity, success/failure
criteria, and privacy classification. Commits and PRs reference that Issue.
The Issue is a coordination/evidence container; opening it does not authorize
execution, acceptance, merge, release, or any other consequential mutation.

### What each stage proves

- **SPECIFIED** — the question, evidence boundary, configuration/data identity,
  and falsifier/criteria are recorded well enough to review.
- **PLANNED** — the execution route, expected artifacts, QA route, recovery
  boundary, and verification plan are explicit.
- **WORKING** — implementation or experiment preparation is in progress. This
  state proves no correctness or scientific claim.
- **QA** — deterministic repository-local checks passed for the exact revision.
  QA does not prove model quality, scientific truth, generalization, or provider
  availability.
- **EXECUTING** — the declared training, evaluation, or other experiment is
  actively running against the exact planned revision/configuration. Runtime
  telemetry and checkpoint/recovery evidence belong here. Execution in progress
  is not yet a model/domain witness.
- **MODEL_OR_DOMAIN_WITNESS** — bounded model/domain evidence was observed for
  the exact artifact/configuration/population declared by the experiment.
  A witness is evidence, not acceptance.
- **REVIEW** — independent or separately routed review findings were recorded
  and blocking findings distinguished from follow-up work.
- **ACCEPTANCE_GATE** — an explicit decision states whether the available QA,
  witness, provenance, and review evidence are sufficient for the declared
  purpose. A green workflow, receipt field, or reviewer comment cannot silently
  substitute for this gate.
- **PROMOTION** — an explicitly authorized mutation moves the accepted change or
  result into its intended authority surface, for example merge to the canonical
  branch or promotion into active guidance.
- **READBACK** — the promoted state is observed from the authoritative target
  and bound to an exact revision/artifact identity. Executor self-report alone is
  insufficient when independent readback is available.
- **DISPOSITION** — the work receives a terminal operational state and unresolved
  findings are linked to their durable destination.

### Terminal exits without promotion

Promotion is conditional, not mandatory. Work may transition directly to
`DISPOSITION` from `SPECIFIED`, `PLANNED`, `WORKING`, `QA`, `EXECUTING`,
`MODEL_OR_DOMAIN_WITNESS`, `REVIEW`, `ACCEPTANCE_GATE`, `PROMOTION`, or
unsuccessful `READBACK` when it is blocked, parked, superseded, abandoned,
partially mutated, or not accepted for promotion.

Typical examples:

```text
SPECIFIED -- abandoned --> DISPOSITION
PLANNED -- superseded --> DISPOSITION
WORKING -- blocked --> DISPOSITION
QA -- blocked --> DISPOSITION
EXECUTING -- failed / blocked --> DISPOSITION
MODEL_OR_DOMAIN_WITNESS -- insufficient / inconclusive --> DISPOSITION
REVIEW -- superseded / parked --> DISPOSITION
ACCEPTANCE_GATE -- declined / no promotion authority --> DISPOSITION
ACCEPTANCE_GATE -- accepted + authorized --> PROMOTION -> READBACK -> DISPOSITION
PROMOTION -- failed / partial --> DISPOSITION
READBACK -- unavailable / mismatch --> DISPOSITION
```

For failed or partial promotion/readback, record the resulting evidence state as
`BLOCKED`, `UNKNOWN`, or `REPROBE_REQUIRED` as applicable, preserve any observed
partial mutation identity, and do not claim `PROMOTED` until authoritative
readback succeeds.

A terminal exit preserves the evidence already produced. It does not fabricate a
promotion/readback event and does not erase a negative or inconclusive research
result.

## Research outcome

The bounded scientific/model result remains one of:

```text
ACCEPTED | REJECTED | INCONCLUSIVE
```

These outcomes are first-class evidence and are independent of branch/PR state.
For example, a scientifically `REJECTED` experiment can still have a
successfully promoted negative-result receipt.

Historical uses of `ACCEPTED | REJECTED | INCONCLUSIVE` remain valid and must
not be reclassified merely because this process contract became more detailed.

## Delivery / branch disposition

A branch, PR, or implementation line should end in an explicit state such as:

```text
PROMOTED | PARKED | SUPERSEDED | ABANDONED | BLOCKED
```

`PARKED`, `SUPERSEDED`, and `ABANDONED` are not deletion instructions.
Important research evidence remains durable even when its implementation path is
no longer active.

## Degraded and external evidence

External providers, hosted runners, marketplaces, APIs, and third-party
verifiers are evidence sources, not implicit authorities.

- **DEGRADED** — a required evidence source or execution surface returned partial
  or lower-quality evidence than the declared route requires.
- **BLOCKED** — a required stage could not be executed or verified.
- **UNKNOWN** — available evidence is insufficient to classify the claim.
- **STALE** — evidence was valid for an earlier revision/runtime but is not
  current proof for the state being accepted.
- **REPROBE_REQUIRED** — the smallest authoritative current-state check must be
  repeated before relying on the evidence.

A provider outage or unavailable verifier must not be converted into PASS.
If degraded evidence is non-blocking for a bounded purpose, that exception is
recorded explicitly at the acceptance gate.

## Evidence binding

Important receipts bind the realized state, not nominal labels:

- exact source/experiment revision;
- realized runtime/configuration and relevant seeds;
- dataset/fixture/evaluation population identity;
- artifact hashes;
- QA route and result;
- witness/evaluation identity;
- review/acceptance disposition;
- promoted target and readback when promotion occurs.

Labels such as branch name, replica name, workflow name, or `accepted=true`
are not sufficient substitutes for realized-state evidence.
