from __future__ import annotations

import collections
import hashlib
import pathlib

SEMANTIC_DECISIONS = {"PROBE", "READY", "UNKNOWN"}
CANONICAL_FIELDS=("applicability","decision","tool_need","evidence_state","cost_class","risk_class")
REGISTERED_CURRICULUM_MANIFEST=pathlib.Path(__file__).resolve().parents[1]/"experiments/needle-stage-c-applicability/manifests/stage-c-curriculum-manifest.json"

def _sha256_path(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in '0123456789abcdef' for ch in value)


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
    canonical_rows = [r for r in rows if r.get("expected_state") is not None]
    canonical_correct = sum(r.get("expected_state") == r.get("predicted_state") for r in canonical_rows)
    field_metrics={}
    for field in CANONICAL_FIELDS:
        confusion=collections.Counter()
        correct=0
        for row in canonical_rows:
            expected_state=row.get("expected_state") or {}
            predicted_state=row.get("predicted_state")
            expected_value=expected_state.get(field,"INVALID")
            predicted_value=predicted_state.get(field,"INVALID") if isinstance(predicted_state,dict) else "INVALID"
            confusion[f"{expected_value}->{predicted_value}"] += 1
            correct += expected_value == predicted_value
        n=len(canonical_rows)
        field_metrics[field]={
            "n":n,"correct":correct,"accuracy":(correct/n) if n else None,
            "confusion":dict(sorted(confusion.items())),
        }
    return {
        "positive_n": len(positives),
        "positive_correct": sum(r.get("predicted") == r.get("expected") for r in positives),
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
        "canonical_field_metrics":field_metrics,
    }


def expected_scope_from_semantic(semantic_rows: list[dict], split: str) -> dict[str, tuple[str, str]]:
    expected = {}
    for row in semantic_rows:
        if row.get("split") != split:
            continue
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in expected:
            raise ValueError(f"invalid registered {split} case ids")
        category = f"{split}_{'positive' if row.get('applicability') == 'route' else 'negative'}"
        decision = row.get("expected_decision") if row.get("applicability") == "route" else "NO_CALL"
        expected[case_id] = (category, decision)
    return expected



def _registered_canonical_state(decision: str) -> dict:
    if decision == "NO_CALL":
        return {
            "applicability":"NONE","decision":"NO_CALL","tool_need":"unnecessary",
            "evidence_state":"sufficient","cost_class":"low","risk_class":"low",
        }
    if decision in SEMANTIC_DECISIONS:
        return {
            "applicability":"ROUTE","decision":decision,"tool_need":"required",
            "evidence_state":"sufficient" if decision == "READY" else "insufficient",
            "cost_class":"low","risk_class":"low",
        }
    raise ValueError("invalid registered route decision")


def _valid_canonical_state(state: dict) -> bool:
    required={"applicability","decision","tool_need","evidence_state","cost_class","risk_class"}
    if not isinstance(state,dict) or set(state) != required:
        return False
    if state["applicability"] not in {"NONE","ROUTE"}: return False
    if state["decision"] not in {"NO_CALL","PROBE","READY","UNKNOWN"}: return False
    if state["applicability"] == "NONE" and state["decision"] != "NO_CALL": return False
    if state["applicability"] == "ROUTE" and state["decision"] not in SEMANTIC_DECISIONS: return False
    if state["tool_need"] not in {"unnecessary","required","helpful","unknown"}: return False
    if state["evidence_state"] not in {"sufficient","insufficient","conflicting"}: return False
    if state["cost_class"] not in {"low","medium","high"}: return False
    if state["risk_class"] not in {"low","medium","high"}: return False
    return True

def validate_scope_rows(rows: list[dict], expected: dict[str, tuple[str, str]], label: str, expected_model_id: str | None = None, expected_weights_sha256: str | None = None, require_canonical_state: bool = False) -> None:
    ids = [row.get("id") for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError(f"{label} evaluation does not contain exact case ids")
    for row in rows:
        category, decision = expected[row["id"]]
        if row.get("category") != category:
            raise ValueError(f"{label} category mismatch for {row['id']}")
        if row.get("expected") != decision:
            raise ValueError(f"{label} expected decision mismatch for {row['id']}")
        if expected_model_id is not None and row.get("model_id") != expected_model_id:
            raise ValueError(f"{label} model_id mismatch for {row['id']}")
        if expected_weights_sha256 is not None and row.get("weights_sha256") != expected_weights_sha256:
            raise ValueError(f"{label} weights sha256 mismatch for {row['id']}")
        if row.get("correct") is not None and bool(row.get("correct")) != (row.get("predicted") == row.get("expected")):
            raise ValueError(f"{label} stale correct field for {row['id']}")
        if require_canonical_state:
            expected_state=row.get("expected_state")
            predicted_state=row.get("predicted_state")
            if not isinstance(expected_state,dict):
                raise ValueError(f"{label} canonical expected state missing for {row['id']}")
            if not _valid_canonical_state(expected_state):
                raise ValueError(f"{label} canonical expected state invalid for {row['id']}")
            if predicted_state != "INVALID" and not _valid_canonical_state(predicted_state):
                raise ValueError(f"{label} canonical state prediction missing or corrupt for {row['id']}")
            if expected_state != _registered_canonical_state(decision):
                raise ValueError(f"{label} expected canonical state mismatch for {row['id']}")
            derived=expected_state == predicted_state
            if row.get("state_correct") is not None and bool(row.get("state_correct")) != derived:
                raise ValueError(f"{label} stale state_correct field for {row['id']}")


def evaluate_replica_pair(arm_a_final_heldout: list[dict], arm_b_early_heldout: list[dict], arm_b_final_heldout: list[dict], arm_a_early_heldout: list[dict] | None = None) -> dict:
    a = scope_metrics(arm_a_final_heldout)
    a_early = scope_metrics(arm_a_early_heldout) if arm_a_early_heldout is not None else None
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
        "arm_a_early": a_early,
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
    r.add_argument('--semantic',type=pathlib.Path,required=True)
    r.add_argument('--arm-a-early',type=pathlib.Path,required=True)
    r.add_argument('--arm-a-early-train',type=pathlib.Path,required=True)
    r.add_argument('--arm-a-final',type=pathlib.Path,required=True)
    r.add_argument('--arm-a-final-train',type=pathlib.Path,required=True)
    r.add_argument('--arm-b-early',type=pathlib.Path,required=True)
    r.add_argument('--arm-b-early-train',type=pathlib.Path,required=True)
    r.add_argument('--arm-b-final',type=pathlib.Path,required=True)
    r.add_argument('--arm-b-final-train',type=pathlib.Path,required=True)
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
        semantic_rows=_load_jsonl_path(args.semantic)
        expected_heldout=expected_scope_from_semantic(semantic_rows,'heldout')
        expected_train=expected_scope_from_semantic(semantic_rows,'train')
        arm_a_early=_load_jsonl_path(args.arm_a_early)
        arm_a_early_train=_load_jsonl_path(args.arm_a_early_train)
        arm_a_final=_load_jsonl_path(args.arm_a_final)
        arm_b_early=_load_jsonl_path(args.arm_b_early)
        arm_b_final=_load_jsonl_path(args.arm_b_final)
        arm_a_final_train=_load_jsonl_path(args.arm_a_final_train)
        arm_b_early_train=_load_jsonl_path(args.arm_b_early_train)
        arm_b_final_train=_load_jsonl_path(args.arm_b_final_train)
        for label, rows in [('arm_a_early_heldout',arm_a_early),('arm_a_final_heldout',arm_a_final),('arm_b_early_heldout',arm_b_early),('arm_b_final_heldout',arm_b_final)]:
            validate_scope_rows(rows,expected_heldout,label)
        for label, rows in [('arm_a_early_train',arm_a_early_train),('arm_a_final_train',arm_a_final_train),('arm_b_early_train',arm_b_early_train),('arm_b_final_train',arm_b_final_train)]:
            validate_scope_rows(rows,expected_train,label)
        evaluation=evaluate_replica_pair(arm_a_final,arm_b_early,arm_b_final,arm_a_early_heldout=arm_a_early)
        evaluation['train_scopes']={
            'arm_a_early':scope_metrics(arm_a_early_train),
            'arm_a_final':scope_metrics(arm_a_final_train),
            'arm_b_early':scope_metrics(arm_b_early_train),
            'arm_b_final':scope_metrics(arm_b_final_train),
        }
        train_a=json.loads(args.arm_a_train_receipt.read_text(encoding='utf-8'))
        train_b=json.loads(args.arm_b_train_receipt.read_text(encoding='utf-8'))
        for expected_arm, train in [('A',train_a),('B',train_b)]:
            if train.get('schema') != 'theseus.needle.stage_c_train.v1':
                raise ValueError('invalid Stage C train receipt schema')
            if train.get('arm_id') != expected_arm or train.get('replica_id') != args.replica_id:
                raise ValueError('Stage C train receipt arm/replica mismatch')
            if train.get('source',{}).get('experiment_commit') != args.experiment_commit:
                raise ValueError('Stage C train receipt experiment mismatch')
            expected_seed={'R1':101,'R2':202}[args.replica_id]
            expected_config={'seed':expected_seed,'epochs':15,'batch_size':16,'lr':1e-4,'lora_rank':16,'lora_alpha':32.0,'max_len':512,'val_split':0.0}
            if train.get('training_config') != expected_config:
                raise ValueError('Stage C train receipt realized config mismatch')
            if train.get('inputs',{}).get('base_checkpoint_sha256') != '4b0a972d163ffc7678fb3c36bace508114872e9d2ce9e10f225825752d3795bc':
                raise ValueError('Stage C train receipt base checkpoint mismatch')
            registered_manifest_sha=_sha256_path(REGISTERED_CURRICULUM_MANIFEST)
            if train.get('inputs',{}).get('curriculum_manifest_sha256') != registered_manifest_sha:
                raise ValueError('Stage C train receipt curriculum manifest mismatch')
        slot_checks=[
            ('arm_a_early_heldout',arm_a_early,f'stage-c-A-{args.replica_id}-early',train_a['artifacts']['early_cact_sha256']),
            ('arm_a_early_train',arm_a_early_train,f'stage-c-A-{args.replica_id}-early',train_a['artifacts']['early_cact_sha256']),
            ('arm_a_final_heldout',arm_a_final,f'stage-c-A-{args.replica_id}-final',train_a['artifacts']['final_cact_sha256']),
            ('arm_a_final_train',arm_a_final_train,f'stage-c-A-{args.replica_id}-final',train_a['artifacts']['final_cact_sha256']),
            ('arm_b_early_heldout',arm_b_early,f'stage-c-B-{args.replica_id}-early',train_b['artifacts']['early_cact_sha256']),
            ('arm_b_early_train',arm_b_early_train,f'stage-c-B-{args.replica_id}-early',train_b['artifacts']['early_cact_sha256']),
            ('arm_b_final_heldout',arm_b_final,f'stage-c-B-{args.replica_id}-final',train_b['artifacts']['final_cact_sha256']),
            ('arm_b_final_train',arm_b_final_train,f'stage-c-B-{args.replica_id}-final',train_b['artifacts']['final_cact_sha256']),
        ]
        for label,rows,model_id,weights_sha256 in slot_checks:
            expected_scope=expected_heldout if label.endswith('_heldout') else expected_train
            validate_scope_rows(rows,expected_scope,label,expected_model_id=model_id,expected_weights_sha256=weights_sha256,require_canonical_state=label.startswith('arm_b_'))
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
            'curriculum_manifest_sha256':registered_manifest_sha,
            'training_evidence':{
                'seed':expected_seed,
                'arm_a_config':train_a['training_config'],
                'arm_b_config':train_b['training_config'],
            },
            'model_artifacts':{
                'arm_a_early_cact_sha256':train_a['artifacts']['early_cact_sha256'],
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
    manifest_sha=r1.get('curriculum_manifest_sha256')
    if not _is_sha256(manifest_sha):
        raise ValueError('final aggregation requires registered curriculum manifest identity')
    if manifest_sha != r2.get('curriculum_manifest_sha256'):
        raise ValueError('replica curriculum manifests differ')
    required_artifacts=(
        'arm_a_early_cact_sha256',
        'arm_a_final_cact_sha256',
        'arm_b_early_cact_sha256',
        'arm_b_final_cact_sha256',
    )
    for expected_replica, receipt, expected_seed in [('R1',r1,101),('R2',r2,202)]:
        evidence=receipt.get('training_evidence')
        if not isinstance(evidence,dict) or evidence.get('seed') != expected_seed:
            raise ValueError(f'{expected_replica} replica seed evidence mismatch')
        for arm_key in ('arm_a_config','arm_b_config'):
            config=evidence.get(arm_key)
            if not isinstance(config,dict) or config.get('seed') != expected_seed:
                raise ValueError(f'{expected_replica} replica {arm_key} seed evidence mismatch')
        artifacts=receipt.get('model_artifacts')
        if not isinstance(artifacts,dict):
            raise ValueError(f'{expected_replica} replica model artifacts missing')
        for artifact_key in required_artifacts:
            if not _is_sha256(artifacts.get(artifact_key)):
                raise ValueError(f'{expected_replica} replica invalid model artifact {artifact_key}')
    for artifact_key in required_artifacts:
        if r1['model_artifacts'][artifact_key] == r2['model_artifacts'][artifact_key]:
            raise ValueError(f'replica model artifact collision: {artifact_key}')
    disposition=final_disposition(r1['evaluation'],r2['evaluation'])
    final={
        'schema':'theseus.needle.stage_c_final.v1',
        'source':{
            'experiment_commit':r1['source']['experiment_commit'],
            'parent_issues':[35,36],
        },
        'curriculum_manifest_sha256':r1.get('curriculum_manifest_sha256'),
        'replicas':{
            'R1':{'evaluation':r1['evaluation'],'model_artifacts':r1['model_artifacts']},
            'R2':{'evaluation':r2['evaluation'],'model_artifacts':r2['model_artifacts']},
        },
        'disposition':disposition,
        'interpretation_boundary':'pre_registered_two_replica_stage_c_disposition',
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(final,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(disposition)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
