# Orchard reference track — teacher trajectories and cumulative agent learning

GitHub Issue: [#6 — teacher trajectories and cumulative agent learning](https://github.com/TeaShaman-cyber/theseus-needle-lab/issues/6)

Research state: `SPECIFIED`

This track studies Orchard as an external reference case for a Needle question:

> Once a small agent can learn at all, can teacher-generated agent trajectories and environment/process feedback provide a better training signal than final labels alone?

This note is an evidence map, not an Orchard reproduction and not evidence that the same effects will transfer to Needle.

## Primary-source snapshot

The source manifest is machine-readable in [`sources.json`](sources.json).

Pinned Orchard repository observation:

```text
repository: https://github.com/microsoft/Orchard
main SHA:   3d7d7e992f56e3fec98f80f52afd7bc2e90af0f4
observed:   2026-08-31
```

Primary references:

- Microsoft Research publication: <https://www.microsoft.com/en-us/research/publication/orchard-an-open-source-agentic-modeling-framework/>
- Microsoft Research blog: <https://www.microsoft.com/en-us/research/blog/orchard-an-open-framework-for-scalable-agentic-ai/>
- arXiv: <https://arxiv.org/abs/2605.15040>
- Orchard repository: <https://github.com/microsoft/Orchard>

## Evidence map

### FACT — teacher trajectories are a first-class training input

The Orchard paper/publication reports that Orchard-SWE distills **107K trajectories** from MiniMax-M2.5 and Qwen3.5-397B, then uses credit-assignment supervised fine-tuning and reinforcement learning starting from Qwen3-30B-A3B-Thinking.

Needle relevance: the training unit is not only a terminal class label; a multi-step agent interaction can itself become training material.

### FACT — partial trajectories can contain useful supervision

Orchard's credit-assignment SFT explicitly learns from productive portions of attempts that did not fully solve the task, rather than treating an unresolved terminal result as wholly useless.

Needle relevance: a failed routing or tool-use episode may still contain locally useful decisions. A future trajectory schema therefore should not collapse the entire episode to one success/failure bit.

### FACT — Orchard-SWE adds denser feedback than terminal verification alone

The Microsoft Research description separates sparse terminal feedback from two denser signals:

- on-policy distillation, where a stronger teacher scores decisions along the student's own behavior;
- a process reward model, where an AI judge evaluates useful problem-solving behavior such as reproducing a bug, verifying the fix, and checking existing behavior.

Needle relevance: a future teacher contract may need to distinguish terminal task outcome from process-level supervision.

### FACT — previous rollouts can become reusable training assets

Microsoft reports training a compact value model on trajectories from prior Orchard-SWE experiments and using it to rerank candidate solutions.

Needle relevance: an experiment trajectory need not be disposable after its original evaluation. With provenance and lifecycle metadata, it can become a reusable research artifact.

### FACT — harness is part of the training distribution

Orchard is built around a reusable environment substrate and describes training/evaluation across real agent harnesses rather than one simplified substitute loop. Orchard-Claw is reported across harnesses including ReACT, ZeroClaw, OpenClaw, and Codex. The Orchard repository also describes an any-harness environment layer.

Needle relevance: `model + harness + environment` should be treated as an experimental configuration, not silently collapsed into “the model”.

## Needle mapping

### Already observed in this research line

- Issue #1 mapped a real executable Needle learning interface.
- A bounded CPU smoke produced a learned artifact on `experiment/needle-cpu-smoke`.
- Issue #4 is evaluating whether that artifact changes held-out routing behavior.
- GitHub Issues, Actions, artifacts, hashes, and receipts provide the traceability substrate.

These facts establish enough infrastructure to ask about training-signal design. They do **not** establish that trajectory supervision is beneficial.

### Missing contracts

Before a teacher-trajectory experiment can be considered reproducible, the lab still needs to define or reuse:

```text
trajectory identity + ordering
teacher model / harness provenance
student model / artifact provenance
environment + tool configuration
per-step supervision representation
terminal outcome representation
privacy / retention class
source and derived artifact hashes
train/eval separation
```

## Smallest future comparison

The first useful Needle experiment should stay smaller than Orchard and hold everything possible constant:

```text
same base Needle learner
same task family
same held-out evaluation
same metric

A: final-label-only training examples
B: teacher-derived trajectory/process examples
```

The exact representation for B is still `UNKNOWN`; it must be derived from Needle's actual accepted training interface rather than invented from Orchard terminology.

A positive B-minus-A result would support only the bounded claim that the richer training signal improved this Needle task distribution. It would not establish general agentic self-improvement, Orchard equivalence, or transfer to unrelated tasks.

## Relationship to other Theseus lines

```text
Session Search
  historical interaction evidence
          |
          v
Memory Provider
  selected retained experience
          |
          v
Needle
  candidate experience as training signal
```

This is an **artifact relationship**, not an authority merger. Session Search history is evidence, Memory Provider output is selected memory, and Needle artifacts are learned-policy evidence. Current truth still requires the appropriate live authority.

## Adjacent evidence, not Orchard claims

The following Microsoft Research work is relevant to later interpretation but is deliberately kept separate from Orchard:

- Replayed-Prefix On-Policy Distillation (ReOPD): reuses pre-collected trajectories as offline prefixes for multi-turn distillation.
- LLM-as-a-Coach / Experiential Learning: studies richer textual experiential feedback instead of reducing evaluation to scalar reward.
- Weak-to-Strong On-Policy Distillation: studies teacher/student capability relationships outside the standard stronger-teacher assumption.

These papers may motivate later hypotheses, but none of them is evidence that Needle will benefit from the same mechanism.

## Current disposition

```text
Orchard mechanism mapping:        FACT-backed reference case
Needle transfer hypothesis:        HYPOTHESIS
Needle trajectory representation:  UNKNOWN
Needle comparative experiment:     NOT RUN
```

Next execution work should wait for a usable baseline/disposition from Issue #4 and then specify the smallest A/B training-signal experiment under Issue #6.
