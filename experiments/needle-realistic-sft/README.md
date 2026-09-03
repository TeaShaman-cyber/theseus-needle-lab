# Needle realistic SFT Stage B

This directory implements the contract-only preparation layer for Issue #26 Stage B.

The authoritative baseline source is `source/families.json`. `scripts/build_realistic_sft_dataset.py` deterministically expands it into repository-authored semantic cases and projects those cases into the frozen Needle route-tool interface. Generated projections and manifests are committed so reviewers can inspect exact bytes and hashes.

The baseline is intentionally isolated from watcher, CI-discovery, web, teacher, and private-session content. Fresh external findings may later form a separately reported post-baseline challenge set, but they do not enter the 360-row training set or the 96-case scientific held-out set.

Current geometry:

```text
train:   100 PROBE + 100 READY + 100 UNKNOWN + 60 NO_CALL = 360
heldout:  24 PROBE +  24 READY +  24 UNKNOWN + 24 NO_CALL =  96
```

The route schema and positive-query prefix are byte-bound to the accepted Stage A predecessor. Validation is fail-closed:

```bash
python3 scripts/build_realistic_sft_dataset.py
python3 scripts/validate_realistic_sft_dataset.py
python3 -m unittest discover -s tests -v
```

`needle-realistic-sft-contract.yml` performs contract validation only. It contains no finetune command and does not authorize a training run.
