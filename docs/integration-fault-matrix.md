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
