# Theseus Needle Lab

Theseus Needle Lab is a public research line under the [Theseus public-interest research program](https://github.com/TeaShaman-cyber/theseus-research). This repository does not define the Theseus program contract.

Its purpose is to make Needle learning experiments observable, reproducible, and verifiable: research intent is recorded before execution, execution is linked to versioned source, and important results carry provenance and verification receipts.

## Research boundary

- Negative and inconclusive results are first-class research outcomes.
- A green GitHub Action proves only the postcondition declared by that workflow; it does not prove model quality, scientific truth, or generalization.
- Training or learning outputs become accepted results only after explicit evaluation and verification.
- Secrets, credentials, private corpora, and user conversation data must not be committed to this public repository or emitted to public logs.
- Public visibility is for research transparency. In the absence of an explicit license, public visibility does not grant open-source reuse rights.
- The first real Needle training CI is a bounded CPU feasibility smoke under Issue #1. It measures the supported `finetune -> build` path and does not establish model quality, scientific validity, or production readiness.

## Research flow

`Issue -> commit/PR -> Action -> artifact/hash -> evaluation -> receipt -> disposition`

See [architecture](docs/architecture.md) and [experiment lifecycle](docs/experiment-lifecycle.md).
