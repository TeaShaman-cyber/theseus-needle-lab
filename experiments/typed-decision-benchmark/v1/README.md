# Typed decision benchmark v1

Issue #56 owns this comparison line. Stage 0 freezes the comparison boundary;
it does not execute any model.

## Suites

primary-24.jsonl is the primary quality suite: 24 new project-synthetic queries,
balanced six each across PROBE, READY, UNKNOWN, and NO_CALL. The exact queries
are verified not to overlap verbatim with the historical compatibility suite or
the current Needle 3 deployment canary.

legacy-compat-24.jsonl is copied byte-for-byte from historical commit
b16dbbb06e3bade0d2e12c3322164006981e6097. It exists for continuity with the old
Needle policy-eval line. It is not a fresh selection set and must not be used to
claim held-out novelty for artifacts that have already been evaluated on it.

## Common semantic boundary

Every system receives the same case semantics. Provider-specific prompts,
choice serialization, tool-call mechanics, and NO_CALL representation may
differ, but each adapter must record those differences in a serialization
receipt and project the result into theseus.typed-decision.v1 before scoring.

The routing benchmark has four expected classes:

- PROBE
- READY
- UNKNOWN
- NO_CALL

ERROR is a measured invalid/execution outcome, never an expected target class.
The drift-sentinel SIGNAL / NO_SIGNAL task is outside benchmark v1.

## Candidate states

The registry distinguishes runnable identities from blocked or unresolved
candidates. RUNTIME_VERIFIED means only that a runtime path was demonstrated;
it is not a quality claim. ACCESS_REQUIRED and CURRENTNESS_PROBE_REQUIRED stay
unmeasured until the missing condition is resolved.

Existing tuned Needle artifacts require an explicit pre-run selection. The
benchmark score must never be used to choose which tuned artifact is evaluated.

## Result projection

A normalized result row records:

- candidate and execution scope;
- one canonical typed-decision envelope;
- optional four-class probabilities;
- latency;
- optional resource receipt reference;
- provider serialization identity, including adapter revision, NO_CALL
  encoding, input/request/response hashes, runtime identity, and model identity.

Self-reported confidence and probability fields are descriptive only. They do
not grant authority, verification, acceptance, or promotion.

## Metrics

The deterministic scorer computes exact accuracy, confusion, UNKNOWN
precision/recall, false-ready, false-probe, negative-control NO_CALL rate,
contract-error rate, escalation frequency, latency, and multiclass Brier score
only when complete normalized probabilities are supplied.

Local and external-provider results remain separate at the receipt level.
Negative and inconclusive runs are preserved.

## Stage 0 disposition

DESIGN_ONLY / NO_MODEL_EXECUTION.

The next step is adapter implementation plus currentness probes for unresolved
candidates, not a quality run.
