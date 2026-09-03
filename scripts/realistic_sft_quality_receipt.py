#!/usr/bin/env python3
from __future__ import annotations

import collections

DECISIONS = {"PROBE", "READY", "UNKNOWN"}


def _scope_metrics(rows: list[dict]) -> dict:
    positives = [r for r in rows if str(r.get("category", "")).endswith("_positive")]
    negatives = [r for r in rows if str(r.get("category", "")).endswith("_negative")]
    valid_calls = [r for r in positives if r.get("predicted") in DECISIONS]
    counts = collections.Counter(r.get("predicted") for r in valid_calls)
    dominant = (max(counts.values()) / len(valid_calls)) if valid_calls else 1.0
    return {
        "positive_n": len(positives),
        "positive_correct": sum(bool(r.get("correct")) for r in positives),
        "positive_accuracy": (sum(bool(r.get("correct")) for r in positives) / len(positives)) if positives else None,
        "positive_route_calls": len(valid_calls),
        "negative_n": len(negatives),
        "negative_no_call": sum(r.get("predicted") == "NO_CALL" for r in negatives),
        "dominant_semantic_decision_rate": dominant,
        "prediction_distribution": dict(sorted(counts.items())),
    }


def evaluate_replica(base_train: list[dict], tuned_train: list[dict], base_heldout: list[dict], tuned_heldout: list[dict]) -> dict:
    bt = _scope_metrics(base_train)
    tt = _scope_metrics(tuned_train)
    bh = _scope_metrics(base_heldout)
    th = _scope_metrics(tuned_heldout)
    if tt["positive_n"] != 300 or th["positive_n"] != 72 or th["negative_n"] != 24:
        raise ValueError("unexpected Stage B evaluation geometry")

    train_fit = tt["positive_correct"] >= 210
    heldout_positive_gain_ok = th["positive_correct"] >= bh["positive_correct"] + 6
    heldout_reachability_ok = th["positive_route_calls"] >= bh["positive_route_calls"] - 3
    heldout_negative_no_call_ok = th["negative_no_call"] >= bh["negative_no_call"] - 2
    dominant_decision_ok = th["dominant_semantic_decision_rate"] <= 0.70
    applicability_regression = not heldout_reachability_ok or not heldout_negative_no_call_ok
    learned_and_generalizes = all([
        train_fit,
        heldout_positive_gain_ok,
        heldout_reachability_ok,
        heldout_negative_no_call_ok,
        dominant_decision_ok,
    ])
    return {
        "train": {"base": bt, "tuned": tt},
        "heldout": {"base": bh, "tuned": th},
        "train_fit": train_fit,
        "heldout_positive_gain_ok": heldout_positive_gain_ok,
        "heldout_reachability_ok": heldout_reachability_ok,
        "heldout_negative_no_call_ok": heldout_negative_no_call_ok,
        "dominant_decision_ok": dominant_decision_ok,
        "applicability_regression": applicability_regression,
        "learned_and_generalizes": learned_and_generalizes,
    }


def final_disposition(r1: dict, r2: dict) -> str:
    if r1.get("applicability_regression") or r2.get("applicability_regression"):
        return "REJECTED_APPLICABILITY_REGRESSION"
    successes = sum(bool(r.get("learned_and_generalizes")) for r in (r1, r2))
    if successes == 2:
        return "ACCEPTED_LEARNED_AND_GENERALIZES"
    if successes == 1:
        return "INCONCLUSIVE_REPLICA_DIVERGENCE"
    if not r1.get("train_fit") and not r2.get("train_fit"):
        return "REJECTED_PERSISTENT_UNDERFIT"
    if r1.get("train_fit") and r2.get("train_fit"):
        return "INCONCLUSIVE_TRAIN_FIT_GENERALIZATION_GAP"
    return "INCONCLUSIVE_REPLICA_DIVERGENCE"

import argparse
import hashlib
import json
import pathlib


def _sha256_path(path: pathlib.Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _load_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def build_replica_receipt(replica_id: str, experiment_commit: str, launcher_commit: str,
                          workflow_run_id: str, evaluation: dict,
                          train_receipt_sha256: str, tuned_cact_sha256: str) -> dict:
    if replica_id not in {'R1','R2'}:
        raise ValueError('invalid replica_id')
    return {
        'schema':'theseus.needle.realistic_sft_replica_eval.v1',
        'replica_id':replica_id,
        'source':{
            'experiment_commit':experiment_commit,
            'launcher_commit':launcher_commit,
            'workflow_run_id':workflow_run_id,
            'parent_issue':26,
        },
        'inputs':{
            'train_receipt_sha256':train_receipt_sha256,
            'tuned_cact_sha256':tuned_cact_sha256,
        },
        'evaluation':evaluation,
        'interpretation_boundary':'paired_behavioral_evaluation_not_cross_replica_aggregation',
    }


def aggregate_receipts(r1: dict, r2: dict) -> dict:
    by_id={r1.get('replica_id'):r1,r2.get('replica_id'):r2}
    if set(by_id) != {'R1','R2'}:
        raise ValueError('final aggregation requires R1 and R2')
    e1=by_id['R1']['evaluation']
    e2=by_id['R2']['evaluation']
    if by_id['R1']['source']['experiment_commit'] != by_id['R2']['source']['experiment_commit']:
        raise ValueError('replica experiment commits differ')
    return {
        'schema':'theseus.needle.realistic_sft_final.v1',
        'source':{
            'experiment_commit':by_id['R1']['source']['experiment_commit'],
            'parent_issue':26,
        },
        'replicas':{
            'R1':{'evaluation':e1,'train_receipt_sha256':by_id['R1']['inputs']['train_receipt_sha256'],'tuned_cact_sha256':by_id['R1']['inputs']['tuned_cact_sha256']},
            'R2':{'evaluation':e2,'train_receipt_sha256':by_id['R2']['inputs']['train_receipt_sha256'],'tuned_cact_sha256':by_id['R2']['inputs']['tuned_cact_sha256']},
        },
        'disposition':final_disposition(e1,e2),
        'interpretation_boundary':'pre_registered_two_replica_stage_b_disposition',
    }


def _main_replica(args) -> int:
    evaluation=evaluate_replica(
        _load_jsonl(args.base_train), _load_jsonl(args.tuned_train),
        _load_jsonl(args.base_heldout), _load_jsonl(args.tuned_heldout),
    )
    receipt=build_replica_receipt(
        args.replica_id,args.experiment_commit,args.launcher_commit,args.run_id,
        evaluation,_sha256_path(args.train_receipt),_sha256_path(args.tuned_cact),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    return 0


def _main_final(args) -> int:
    r1=json.loads(args.r1.read_text(encoding='utf-8'))
    r2=json.loads(args.r2.read_text(encoding='utf-8'))
    receipt=aggregate_receipts(r1,r2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(receipt['disposition'])
    return 0


def main() -> int:
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest='command',required=True)
    r=sub.add_parser('replica')
    for name in ['base-train','tuned-train','base-heldout','tuned-heldout','train-receipt','tuned-cact','output']:
        r.add_argument('--'+name,type=pathlib.Path,required=True)
    r.add_argument('--replica-id',required=True)
    r.add_argument('--experiment-commit',required=True)
    r.add_argument('--launcher-commit',required=True)
    r.add_argument('--run-id',required=True)
    f=sub.add_parser('final')
    f.add_argument('--r1',type=pathlib.Path,required=True)
    f.add_argument('--r2',type=pathlib.Path,required=True)
    f.add_argument('--output',type=pathlib.Path,required=True)
    a=p.parse_args()
    return _main_replica(a) if a.command=='replica' else _main_final(a)

if __name__ == '__main__':
    raise SystemExit(main())
