#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib

SCHEMA = 'theseus.needle.realistic_sft_replica_train.v1'


def build_receipt(*, replica_id: str, experiment_commit: str, launcher_commit: str,
                  workflow_run_id: str, train_sha256: str, checkpoint_sha256: str,
                  adapter_sha256: str, cact_sha256: str,
                  train_elapsed_seconds: float, train_max_rss_kb: int,
                  build_elapsed_seconds: float) -> dict:
    if replica_id not in {'R1','R2'}:
        raise ValueError('invalid replica_id')
    return {
        'schema': SCHEMA,
        'replica_id': replica_id,
        'source': {
            'experiment_commit': experiment_commit,
            'launcher_commit': launcher_commit,
            'workflow_run_id': workflow_run_id,
            'parent_issue': 26,
        },
        'config': {
            'cactus_needle': '2.0.8', 'seed': 0, 'epochs': 15, 'batch_size': 16,
            'lr': 1e-4, 'lora_rank': 16, 'lora_alpha': 32, 'max_len': 256,
            'val_split': 0.1, 'workers': 1,
        },
        'inputs': {
            'train_sha256': train_sha256,
            'checkpoint_sha256': checkpoint_sha256,
        },
        'artifacts': {
            'adapter_sha256': adapter_sha256,
            'cact_sha256': cact_sha256,
        },
        'resources': {
            'train_elapsed_seconds': train_elapsed_seconds,
            'train_max_rss_kb': train_max_rss_kb,
            'build_elapsed_seconds': build_elapsed_seconds,
        },
        'interpretation_boundary': 'training_execution_receipt_not_model_quality_evidence',
    }


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--replica-id', required=True)
    p.add_argument('--experiment-commit', required=True)
    p.add_argument('--launcher-commit', required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--train-sha256', required=True)
    p.add_argument('--checkpoint-sha256', required=True)
    p.add_argument('--adapter-sha256', required=True)
    p.add_argument('--cact-sha256', required=True)
    p.add_argument('--train-elapsed-seconds', type=float, required=True)
    p.add_argument('--train-max-rss-kb', type=int, required=True)
    p.add_argument('--build-elapsed-seconds', type=float, required=True)
    p.add_argument('--output', type=pathlib.Path, required=True)
    a=p.parse_args()
    receipt=build_receipt(
        replica_id=a.replica_id, experiment_commit=a.experiment_commit,
        launcher_commit=a.launcher_commit, workflow_run_id=a.run_id,
        train_sha256=a.train_sha256, checkpoint_sha256=a.checkpoint_sha256,
        adapter_sha256=a.adapter_sha256, cact_sha256=a.cact_sha256,
        train_elapsed_seconds=a.train_elapsed_seconds,
        train_max_rss_kb=a.train_max_rss_kb, build_elapsed_seconds=a.build_elapsed_seconds,
    )
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(receipt, sort_keys=True, indent=2)+'\n', encoding='utf-8')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
