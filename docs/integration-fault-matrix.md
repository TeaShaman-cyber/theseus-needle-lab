# Integration fault matrix

This contract gives Needle deployment and helper failures a stable vocabulary
without turning infrastructure evidence into scientific conclusions.

The taxonomy has two kinds of entries. An infrastructure_fault maps an observed
execution, artifact, or authoritative-readback problem to BLOCKED, DEGRADED,
UNKNOWN, or REPROBE_REQUIRED. A bounded_witness records a verified
semantic/performance divergence as MODEL_OR_DOMAIN_WITNESS.

A bounded witness is not an ACCEPTED or REJECTED research outcome, and it is not
a generic PASS or NO_CALL result. Those decisions belong to the experiment's own
acceptance gate.

## Mechanical checkpoint classification

Only evidence readable directly from the promoted execution checkpoint is
classified automatically:

- nonzero terminal exit becomes EXECUTION_FAILED / BLOCKED;
- terminal signal becomes EXECUTION_INTERRUPTED / BLOCKED;
- a still-running checkpoint becomes EXECUTION_AMBIGUOUS / UNKNOWN;
- a successful command with incomplete artifact scanning becomes
  ARTIFACT_PROVENANCE_INCOMPLETE / DEGRADED;
- a healthy successful and complete checkpoint yields no fault.

Semantic mismatch, quantization/export divergence, helper/verifier exactness
loss, call-rate collapse, and performance inversion require an explicit observed
comparison. The helper never infers them from missing evidence.

## Receipt binding

Fault receipts reuse the promoted execution contract:

- exact experiment and launcher SHAs;
- run ID, run attempt, stage, and unit;
- execution, lifecycle, and artifact-scan state;
- command exit and signal;
- verified artifact identities;
- SHA-256 of the execution checkpoint.

The mapped state comes from the versioned taxonomy. Receipt validation rejects a
tampered mapping.

## Failure upload and readback

The recovery canary creates a fault receipt after its deliberate downstream
failure. Its existing always-run artifact upload carries telemetry, recoverable
artifacts, and the fault receipt. A second job downloads the bundle and validates
both the execution checkpoint and the fault receipt against that exact
checkpoint.

This proves transport and contract mechanics only. It does not prove model
quality or a current Needle 3 deployment divergence.

## Needle 3 consumer boundary

The #61/#65 canary can build explicit bounded-witness receipts from observed
reference/candidate comparisons. A missing built artifact or unavailable
readback remains an infrastructure state and must never be converted into
NO_CURRENT_SIGNAL or an invented successful NO_CALL observation.

Receipts bind both the taxonomy version and a canonical SHA-256 digest of the
taxonomy content. A same-version taxonomy edit therefore cannot silently
reinterpret an older receipt.

Partial artifact provenance preserves the execution checkpoint's artifact scan
errors so downstream consumers can distinguish a verified artifact set from
incomplete provenance without guessing why the scan was partial.

## Exactness hardening

A receipt marked CHECKPOINT_DERIVED must reproduce the same mechanical fault
class when its bound execution checkpoint is classified again. Binding only the
checkpoint bytes is not sufficient if the receipt can reinterpret those bytes as
a different fault.

Execution checkpoint projections are also checked for internal consistency:
terminal status must agree with exit/signal evidence, scan COMPLETE cannot carry
scan errors, scan PARTIAL must carry errors, and artifact-provenance lifecycle
state must agree with the presence of artifact identities.

ARTIFACT_MISSING requires VERIFIED evidence; partial absence is provenance
incompleteness rather than proof that the artifact is missing. INVALID_IDENTITY
requires an explicit observed-versus-expected comparison.

The CLI does not print a bound VALID=PASS for checkpoint-dependent receipts unless
the checkpoint is supplied and the receipt is validated against it.

The lifecycle mapped-state set is canonical in the validator; the taxonomy file
cannot authorize a new state by listing it itself. Each fault class also declares
its allowed classification source. Mechanical execution classes are
CHECKPOINT_DERIVED only; comparison, artifact/readback, and bounded-witness
classes are EXPLICIT_OBSERVATION only.

Each taxonomy class also names required_next_evidence. This is an epistemic
handoff field, not an authority-bearing action: it says what evidence would
resolve or advance the state without instructing the next agent to merge,
promote, accept, or reject anything. In particular, UNKNOWN names the missing
terminal/readback evidence instead of becoming an undifferentiated dead end.
