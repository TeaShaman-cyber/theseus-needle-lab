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

Artifact snapshots intentionally exclude hidden files and files beneath hidden
artifact roots to match the default actions/upload-artifact behavior, and skip
symlinks instead of following them.
Per-artifact stat/hash failures are recorded as partial scan evidence instead of
replacing the wrapped command's exit status. The terminal command status is
persisted before artifact scanning begins, so a scanner or filesystem race cannot
leave a completed command reported as RUNNING.

The production launcher cadence is five minutes. Heartbeats are deliberately small
JSONL state records, not full process telemetry. Hard runner cancellation or job
timeout may prevent the final checkpoint and upload; such recovery remains UNKNOWN
or REPROBE_REQUIRED.

GitHub artifact retention is finite. An uploaded checkpoint is execution evidence,
not durable authority by itself. Important promoted evidence still follows normal
repository persistence and authoritative readback.

Artifact hashing is accepted as complete only when device/inode/size and
nanosecond mtime/ctime metadata remain unchanged across the hash read. Concurrent
mutation is recorded as partial scan evidence.

The terminal command checkpoint is paired with a terminal heartbeat before
artifact scanning begins. Validation requires the final heartbeat execution,
lifecycle, and artifact-scan states to match the checkpoint as well as its
sequence and identity.

Hosted recovery canary artifacts are keyed by both GitHub run ID and run attempt,
so rerunning the same workflow execution cannot collide with immutable artifacts
from an earlier attempt.
