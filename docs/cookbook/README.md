# Needle Project Cookbook

This is the repository-local operational/scientific recall index for Theseus Needle Lab.

It is intentionally small. Detailed experiment narratives, raw logs, and candidate hypotheses stay in Issues, PRs, receipts, and the existing repository documentation.

Use rules from this file only from an accepted repository revision applicable to the work being performed.

## Active rules

### NDL-001 — Execution success is not scientific acceptance

A successful GitHub Action, training process, artifact upload, or other execution step proves only its declared execution postcondition.

Scientific acceptance requires the repository's separate evaluation and verification steps. Do not turn a green workflow into a model-quality, generalization, or research-truth claim.

Evidence basis:
- `README.md` — Research boundary
- `docs/experiment-lifecycle.md`

### NDL-002 — Bind execution and artifacts to exact identity

Experiment execution must bind the exact source revision being tested.

Receipts preserve the relevant provenance identities and verification state they attest to. Important artifacts preserve recorded SHA-256 content hashes. Do not substitute a local branch name, stale tracking ref, launcher revision, or storage location for the exact experiment or artifact identity.

Evidence basis:
- `docs/architecture.md`
- `docs/experiment-lifecycle.md`

### NDL-003 — Preserve inconclusive outcomes

Keep `ACCEPTED`, `REJECTED`, and `INCONCLUSIVE` distinct.

`REJECTED` and `INCONCLUSIVE` are preserved outcomes, not failures of record keeping. Do not silently rewrite one disposition as another or infer scientific acceptance from execution success.

Evidence basis:
- `README.md`
- `docs/experiment-lifecycle.md`
- `docs/architecture.md`

## Candidate lessons

Candidate lessons are not active guidance.

New observations from an Issue, PR, CI run, reviewer comment, or local worktree remain evidence until currentness and applicability are checked and the lesson is promoted through a reviewed repository change.

Do not copy a candidate workaround into the active rules merely because it worked once.

## Scope boundary

This cookbook covers Needle-specific scientific, CI, provenance, and experiment-workflow procedures.

Runtime-specific MarcoPolo transport, shell, connector, persistence, and tool-routing guidance belongs in the MarcoPolo runtime cookbook.

When both layers apply, compose by concern. If they conflict on the same concern and current authoritative evidence does not resolve the conflict, stop with `BLOCKED` rather than inventing precedence.
