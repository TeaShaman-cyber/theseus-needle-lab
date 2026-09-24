# Typed System-1 decision contract v1

Issue #55 owns the canonical semantics in this repository. This contract is a
bounded interface for cheap learned decisions. It is not an authority surface.

## Core routing decisions

PROBE means the task is applicable, current verification is still required,
and a safe bounded probe is available.

READY means current authoritative evidence supports the requested state under
the supplied decision context. A learned READY is still only a proposal. It
does not promote runtime state to VERIFIED and does not grant permission,
accept an experiment, authorize a merge, release, or mutation.

UNKNOWN means the task is applicable but available evidence is insufficient
and no safe/sufficient current probe is available. UNKNOWN is not NO_CALL.

NO_CALL means the evidence-routing task is not applicable to the input. It is
a legitimate negative-control outcome, not uncertainty and not an error.

ERROR is an invalid parse, malformed model output, execution failure, or other
contract failure. It is separate from READY, PROBE, UNKNOWN, and NO_CALL.

## Drift sentinel compatibility

Issue #5 is proposal-only: a drift watcher may emit a SIGNAL or emit NO_SIGNAL.
Current main and issue history do not contain a versioned machine output
envelope for #5, so v1 records semantic compatibility only. It does not claim
that a historical #5 receipt was migrated.

Signal names remain task-specific strings in v1. The contract intentionally
does not freeze the future #5 drift taxonomy.

## Confidence

advisory_confidence never carries authority.

UNAVAILABLE means no meaningful confidence value is exposed. Historical tuned
Needle evaluation intentionally produced confidence=None because LoRA did not
update the confidence head; v1 maps that to kind=UNAVAILABLE, value=null,
calibrated=false.

MODEL_REPORTED is an uncalibrated model-reported number in [0,1].
CALIBRATED_POSTHOC is reserved for a separately measured calibration layer.

Neither form may be used as proof of VERIFIED state, permission, acceptance,
or promotion authority.

## Evidence, currentness, escalation, and authority

evidence_refs and currentness_refs are opaque references to evidence used by
the decision. They do not make that evidence authoritative by themselves.

PROBE includes a probe kind and optional route target. UNKNOWN carries an
explicit escalation reason. Historical routing outputs that did not encode the
reason may use LEGACY_UNSPECIFIED during projection rather than inventing one.

authority_required says whether the downstream action requires authority. The
flag never means authority is present, granted, or satisfied. Mutation and
consequential promotion remain outside the learned decision layer.

extensions is a non-authoritative compatibility envelope for later bounded
context such as resource/runtime references. Extension data cannot override the
core outcome semantics or authority boundary.

## Historical mapping

Issue #26 legacy labels preserve their historical meanings:

- PROBE, READY, UNKNOWN map to DECISION with the same decision value.
- NO_CALL maps to the dedicated NO_CALL outcome.
- INVALID maps to ERROR with code INVALID_MODEL_OUTPUT.
- tuned confidence=None maps to advisory confidence UNAVAILABLE.

Issue #5 has no versioned machine output on current main. Its proposal
semantics map only at the compatibility level: drift proposal to SIGNAL and
no-drift/abstain to NO_SIGNAL.

The exact machine mapping is versioned in
contracts/typed-decision/legacy-mapping.v1.json.

## Evaluation boundary

The synthetic fixtures cover current, stale, conflicting, insufficient,
negative-control, drift-signal, no-signal, and invalid-output cases. External
models may serialize prompts differently, but comparison under issue #56 must
project their results into this envelope before metrics are compared.

A model, adapter, heuristic, or provider may produce this envelope. None of
them acquires mutation, verification, acceptance, merge, release, or permission
authority by doing so.
