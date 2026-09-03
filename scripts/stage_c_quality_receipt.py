from __future__ import annotations

import collections

SEMANTIC_DECISIONS = {"PROBE", "READY", "UNKNOWN"}


def _expected_applicability(row: dict) -> str:
    return "NONE" if row.get("expected") == "NO_CALL" else "ROUTE"


def _predicted_applicability(row: dict) -> str:
    predicted = row.get("predicted")
    if predicted == "NO_CALL":
        return "NONE"
    if predicted in SEMANTIC_DECISIONS:
        return "ROUTE"
    return "INVALID"


def scope_metrics(rows: list[dict]) -> dict:
    positives = [r for r in rows if str(r.get("category", "")).endswith("_positive")]
    negatives = [r for r in rows if str(r.get("category", "")).endswith("_negative")]

    app_conf = collections.Counter()
    semantic_conf = collections.Counter()
    semantic_predictions = collections.Counter()
    runtime_or_invalid = 0
    observed_valid_applicability = set()

    for row in rows:
        expected_app = _expected_applicability(row)
        predicted_app = _predicted_applicability(row)
        app_conf[f"{expected_app}->{predicted_app}"] += 1
        if predicted_app in {"NONE", "ROUTE"}:
            observed_valid_applicability.add(predicted_app)
        else:
            runtime_or_invalid += 1

        if expected_app == "ROUTE" and row.get("predicted") in SEMANTIC_DECISIONS:
            semantic_conf[f"{row.get('expected')}->{row.get('predicted')}"] += 1
            semantic_predictions[row.get("predicted")] += 1

    semantic_total = sum(semantic_predictions.values())
    dominant = max(semantic_predictions.values()) / semantic_total if semantic_total else 1.0
    canonical_rows = [r for r in rows if r.get("state_correct") is not None]
    canonical_correct = sum(bool(r.get("state_correct")) for r in canonical_rows)
    return {
        "positive_n": len(positives),
        "positive_correct": sum(bool(r.get("correct")) for r in positives),
        "negative_n": len(negatives),
        "negative_no_call": sum(r.get("predicted") == "NO_CALL" for r in negatives),
        "applicability_confusion": dict(sorted(app_conf.items())),
        "semantic_confusion": dict(sorted(semantic_conf.items())),
        "semantic_prediction_distribution": dict(sorted(semantic_predictions.items())),
        "dominant_semantic_decision_rate": dominant,
        "applicability_observed_classes": sorted(observed_valid_applicability),
        "runtime_or_invalid": runtime_or_invalid,
        "canonical_state_n": len(canonical_rows),
        "canonical_state_correct": canonical_correct,
        "canonical_state_accuracy": (canonical_correct / len(canonical_rows)) if canonical_rows else None,
    }


def evaluate_replica_pair(arm_a_final_heldout: list[dict], arm_b_early_heldout: list[dict], arm_b_final_heldout: list[dict]) -> dict:
    a = scope_metrics(arm_a_final_heldout)
    early = scope_metrics(arm_b_early_heldout)
    final = scope_metrics(arm_b_final_heldout)

    if (a["positive_n"], a["negative_n"]) != (72, 24):
        raise ValueError("unexpected Arm A final heldout geometry")
    if (early["positive_n"], early["negative_n"]) != (72, 24):
        raise ValueError("unexpected Arm B early heldout geometry")
    if (final["positive_n"], final["negative_n"]) != (72, 24):
        raise ValueError("unexpected Arm B final heldout geometry")

    recovery_floor_ok = final["negative_no_call"] >= 20
    positive_floor_ok = final["positive_correct"] >= 32
    dominant_semantic_ok = final["dominant_semantic_decision_rate"] <= 0.70
    applicability_not_collapsed = len(final["applicability_observed_classes"]) >= 2
    reduced_weight_retention_ok = (
        early["negative_no_call"] >= 20
        and final["negative_no_call"] >= 20
    )
    paired_specificity_ok = (
        final["negative_no_call"] > a["negative_no_call"]
        and final["positive_correct"] >= a["positive_correct"]
    )

    if not recovery_floor_ok or not reduced_weight_retention_ok:
        disposition = "REJECTED_APPLICABILITY_RECOVERY_FAILED"
    elif not positive_floor_ok:
        disposition = "REJECTED_POSITIVE_RETENTION_REGRESSION"
    elif not dominant_semantic_ok or not applicability_not_collapsed:
        disposition = "REJECTED_DECISION_COLLAPSE"
    elif not paired_specificity_ok:
        disposition = "INCONCLUSIVE_RECOVERY_SPECIFICITY"
    else:
        disposition = "ACCEPTED_REPLICA_STAGE_C_APPLICABILITY_RECOVERY"

    accepted = disposition == "ACCEPTED_REPLICA_STAGE_C_APPLICABILITY_RECOVERY"
    return {
        "arm_a_final": a,
        "arm_b_early": early,
        "arm_b_final": final,
        "recovery_floor_ok": recovery_floor_ok,
        "positive_floor_ok": positive_floor_ok,
        "dominant_semantic_ok": dominant_semantic_ok,
        "applicability_not_collapsed": applicability_not_collapsed,
        "reduced_weight_retention_ok": reduced_weight_retention_ok,
        "paired_specificity_ok": paired_specificity_ok,
        "accepted": accepted,
        "disposition": disposition,
    }


def final_disposition(r1: dict, r2: dict) -> str:
    if r1.get("accepted") and r2.get("accepted"):
        return "ACCEPTED_STAGE_C_APPLICABILITY_RECOVERY"
    priority = [
        "REJECTED_APPLICABILITY_RECOVERY_FAILED",
        "REJECTED_POSITIVE_RETENTION_REGRESSION",
        "REJECTED_DECISION_COLLAPSE",
        "INCONCLUSIVE_RECOVERY_SPECIFICITY",
    ]
    observed = {r1.get("disposition"), r2.get("disposition")}
    for disposition in priority:
        if disposition in observed:
            return disposition
    return "INCONCLUSIVE_REPLICA_DIVERGENCE"


def _load_jsonl_path(path):
    import json
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def main() -> int:
    import argparse
    import json
    import pathlib
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest='command',required=True)
    r=sub.add_parser('replica')
    r.add_argument('--arm-a-final',type=pathlib.Path,required=True)
    r.add_argument('--arm-b-early',type=pathlib.Path,required=True)
    r.add_argument('--arm-b-final',type=pathlib.Path,required=True)
    r.add_argument('--arm-a-train-receipt',type=pathlib.Path,required=True)
    r.add_argument('--arm-b-train-receipt',type=pathlib.Path,required=True)
    r.add_argument('--replica-id',choices=['R1','R2'],required=True)
    r.add_argument('--experiment-commit',required=True)
    r.add_argument('--launcher-commit',required=True)
    r.add_argument('--run-id',required=True)
    r.add_argument('--output',type=pathlib.Path,required=True)
    f=sub.add_parser('final')
    f.add_argument('--r1',type=pathlib.Path,required=True)
    f.add_argument('--r2',type=pathlib.Path,required=True)
    f.add_argument('--output',type=pathlib.Path,required=True)
    args=p.parse_args()
    if args.command=='replica':
        evaluation=evaluate_replica_pair(
            _load_jsonl_path(args.arm_a_final),
            _load_jsonl_path(args.arm_b_early),
            _load_jsonl_path(args.arm_b_final),
        )
        train_a=json.loads(args.arm_a_train_receipt.read_text(encoding='utf-8'))
        train_b=json.loads(args.arm_b_train_receipt.read_text(encoding='utf-8'))
        for expected_arm, train in [('A',train_a),('B',train_b)]:
            if train.get('schema') != 'theseus.needle.stage_c_train.v1':
                raise ValueError('invalid Stage C train receipt schema')
            if train.get('arm_id') != expected_arm or train.get('replica_id') != args.replica_id:
                raise ValueError('Stage C train receipt arm/replica mismatch')
            if train.get('source',{}).get('experiment_commit') != args.experiment_commit:
                raise ValueError('Stage C train receipt experiment mismatch')
        receipt={
            'schema':'theseus.needle.stage_c_replica_eval.v1',
            'replica_id':args.replica_id,
            'source':{
                'experiment_commit':args.experiment_commit,
                'launcher_commit':args.launcher_commit,
                'workflow_run_id':args.run_id,
                'parent_issues':[35,36],
            },
            'evaluation':evaluation,
            'model_artifacts':{
                'arm_a_final_cact_sha256':train_a['artifacts']['final_cact_sha256'],
                'arm_b_early_cact_sha256':train_b['artifacts']['early_cact_sha256'],
                'arm_b_final_cact_sha256':train_b['artifacts']['final_cact_sha256'],
            },
            'interpretation_boundary':'paired_stage_c_applicability_recovery_with_early_and_final_b_checkpoints',
        }
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        print(evaluation['disposition'])
        return 0
    r1=json.loads(args.r1.read_text(encoding='utf-8'))
    r2=json.loads(args.r2.read_text(encoding='utf-8'))
    if {r1.get('replica_id'),r2.get('replica_id')} != {'R1','R2'}:
        raise ValueError('final aggregation requires R1 and R2')
    if r1['source']['experiment_commit'] != r2['source']['experiment_commit']:
        raise ValueError('replica experiment commits differ')
    disposition=final_disposition(r1['evaluation'],r2['evaluation'])
    final={
        'schema':'theseus.needle.stage_c_final.v1',
        'source':{
            'experiment_commit':r1['source']['experiment_commit'],
            'parent_issues':[35,36],
        },
        'replicas':{'R1':r1['evaluation'],'R2':r2['evaluation']},
        'disposition':disposition,
        'interpretation_boundary':'pre_registered_two_replica_stage_c_disposition',
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(final,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(disposition)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
