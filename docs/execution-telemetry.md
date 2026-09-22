# Execution telemetry and recovery checkpoints

The execution telemetry contract is a lightweight evidence envelope for long-running
Needle jobs. It does not change training semantics and it is not a model/domain
witness.

The v1 checkpoint binds the exact experiment and launcher revisions, run identity,
stage and bounded unit identity, execution status, lifecycle state, bounded
heartbeat sequence, shell-compatible exit code, terminating signal when applicable, and hashes of
recoverable artifacts that actually exist.

A failed command may still reach ARTIFACT_PROVENANCE when a useful partial
artifact was produced before the failure. That does not turn execution into a
PASS. It records only what can be recovered and independently read back.

Artifact snapshots intentionally exclude hidden files to match the default
actions/upload-artifact behavior, and skip symlinks instead of following them.
Artifact scanning must not replace the wrapped command's exit status.

The production launcher cadence is five minutes. Heartbeats are deliberately small
JSONL state records, not full process telemetry. Hard runner cancellation or job
timeout may prevent the final checkpoint and upload; such recovery remains UNKNOWN
or REPROBE_REQUIRED.

GitHub artifact retention is finite. An uploaded checkpoint is execution evidence,
not durable authority by itself. Important promoted evidence still follows normal
repository persistence and authoritative readback.
