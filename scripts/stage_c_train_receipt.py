#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib


def sha256_path(path: pathlib.Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--arm-id',choices=['A','B'],required=True)
    p.add_argument('--replica-id',choices=['R1','R2'],required=True)
    p.add_argument('--experiment-commit',required=True)
    p.add_argument('--launcher-commit',required=True)
    p.add_argument('--run-id',required=True)
    p.add_argument('--early-adapter',type=pathlib.Path,required=True)
    p.add_argument('--early-cact',type=pathlib.Path,required=True)
    p.add_argument('--final-adapter',type=pathlib.Path,required=True)
    p.add_argument('--final-cact',type=pathlib.Path,required=True)
    p.add_argument('--curriculum-manifest',type=pathlib.Path,required=True)
    p.add_argument('--checkpoint',type=pathlib.Path,required=True)
    p.add_argument('--seed',type=int,required=True)
    p.add_argument('--epochs',type=int,required=True)
    p.add_argument('--batch-size',type=int,required=True)
    p.add_argument('--lr',type=float,required=True)
    p.add_argument('--lora-rank',type=int,required=True)
    p.add_argument('--lora-alpha',type=float,required=True)
    p.add_argument('--max-len',type=int,required=True)
    p.add_argument('--val-split',type=float,required=True)
    p.add_argument('--output',type=pathlib.Path,required=True)
    a=p.parse_args()
    for path in [a.early_adapter,a.early_cact,a.final_adapter,a.final_cact,a.curriculum_manifest,a.checkpoint]:
        if not path.is_file():
            raise FileNotFoundError(path)
    expected_seed={'R1':101,'R2':202}[a.replica_id]
    expected_config={'seed':expected_seed,'epochs':15,'batch_size':16,'lr':1e-4,'lora_rank':16,'lora_alpha':32.0,'max_len':512,'val_split':0.0}
    realized_config={'seed':a.seed,'epochs':a.epochs,'batch_size':a.batch_size,'lr':a.lr,'lora_rank':a.lora_rank,'lora_alpha':a.lora_alpha,'max_len':a.max_len,'val_split':a.val_split}
    if realized_config != expected_config:
        raise ValueError(f'realized Stage C training config mismatch: expected {expected_config}, got {realized_config}')
    receipt={
        'schema':'theseus.needle.stage_c_train.v1',
        'arm_id':a.arm_id,
        'replica_id':a.replica_id,
        'source':{
            'experiment_commit':a.experiment_commit,
            'launcher_commit':a.launcher_commit,
            'workflow_run_id':a.run_id,
            'parent_issues':[35,36],
        },
        'inputs':{
            'curriculum_manifest_sha256':sha256_path(a.curriculum_manifest),
            'base_checkpoint_sha256':sha256_path(a.checkpoint),
        },
        'training_config':{
            **realized_config,
        },
        'artifacts':{
            'early_adapter_sha256':sha256_path(a.early_adapter),
            'early_cact_sha256':sha256_path(a.early_cact),
            'final_adapter_sha256':sha256_path(a.final_adapter),
            'final_cact_sha256':sha256_path(a.final_cact),
        },
        'interpretation_boundary':'training_artifact_identity_not_quality_acceptance',
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'arm_id':a.arm_id,'replica_id':a.replica_id,'status':'BOUND'},sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
