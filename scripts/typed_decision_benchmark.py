#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import validate_typed_decision_contract as contract
DEFAULT_MANIFEST = ROOT / 'experiments' / 'typed-decision-benchmark' / 'v1' / 'manifest.json'
CLASSES = ('PROBE', 'READY', 'UNKNOWN', 'NO_CALL')
PREDICTIONS = (*CLASSES, 'ERROR')


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f'non-object JSONL row in {path}')
            rows.append(value)
    return rows


def validate_cases(path: Path, *, primary: bool) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    if len(rows) != 24:
        raise ValueError(f'expected 24 cases in {path}, got {len(rows)}')
    ids = [row.get('case_id', row.get('id')) for row in rows]
    if any(not isinstance(value, str) or not value for value in ids):
        raise ValueError('case id missing')
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate case id')
    queries = [row.get('query') for row in rows]
    if any(not isinstance(value, str) or not value for value in queries):
        raise ValueError('query missing')
    if len(queries) != len(set(queries)):
        raise ValueError('duplicate query')
    labels = [row.get('expected') for row in rows]
    if collections.Counter(labels) != collections.Counter({label: 6 for label in CLASSES}):
        raise ValueError(f'unbalanced labels: {collections.Counter(labels)}')
    if primary:
        for row in rows:
            if row.get('source_kind') != 'project_synthetic_primary_v1':
                raise ValueError('primary source_kind mismatch')
            if not isinstance(row.get('family'), str) or not row['family']:
                raise ValueError('primary family missing')
    return rows


def validate_candidates(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != 'theseus.typed-decision-benchmark-candidates.v1':
        raise ValueError('candidate schema mismatch')
    candidates = data.get('candidates')
    if not isinstance(candidates, dict) or not candidates:
        raise ValueError('candidate registry missing')
    allowed = {
        'IMPLEMENTATION_REQUIRED',
        'RUNTIME_IDENTITY_VERIFIED',
        'ARTIFACT_SELECTION_REQUIRED',
        'RUNTIME_VERIFIED',
        'BLOCKED_STANDARD_CPU',
        'ACCESS_REQUIRED',
        'CURRENTNESS_PROBE_REQUIRED',
    }
    for candidate_id, item in candidates.items():
        if not candidate_id or not isinstance(item, dict):
            raise ValueError('candidate entry invalid')
        if item.get('status') not in allowed:
            raise ValueError(f'candidate status invalid: {candidate_id}')
        if item.get('execution_scope') not in {'LOCAL_REPRODUCIBLE', 'EXTERNAL_PROVIDER'}:
            raise ValueError(f'candidate execution_scope invalid: {candidate_id}')
    return data


def validate_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != 'theseus.typed-decision-benchmark-manifest.v1':
        raise ValueError('manifest schema mismatch')
    if data.get('task') != 'EVIDENCE_ROUTING':
        raise ValueError('benchmark v1 is routing-only')
    contract_spec = data['contract']
    contract_path = ROOT / contract_spec['path']
    if sha256_file(contract_path) != contract_spec['sha256']:
        raise ValueError('contract digest mismatch')

    primary_spec = data['primary_suite']
    legacy_spec = data['legacy_compat_suite']
    registry_spec = data['candidate_registry']
    primary_path = ROOT / primary_spec['path']
    legacy_path = ROOT / legacy_spec['path']
    registry_path = ROOT / registry_spec['path']
    if sha256_file(primary_path) != primary_spec['sha256']:
        raise ValueError('primary suite digest mismatch')
    if sha256_file(legacy_path) != legacy_spec['sha256']:
        raise ValueError('legacy suite digest mismatch')
    if sha256_file(registry_path) != registry_spec['sha256']:
        raise ValueError('candidate registry digest mismatch')

    primary = validate_cases(primary_path, primary=True)
    legacy = validate_cases(legacy_path, primary=False)
    if set(row['query'] for row in primary) & set(row['query'] for row in legacy):
        raise ValueError('primary query overlaps legacy suite verbatim')

    current_canary = read_jsonl(
        ROOT / 'experiments' / 'needle3-deployment-canary' / 'v1' / 'cases.jsonl'
    )
    if set(row['query'] for row in primary) & set(row['query'] for row in current_canary):
        raise ValueError('primary query overlaps current Needle canary verbatim')

    validate_candidates(registry_path)
    if data['run_policy'].get('stage0_executes_models') is not False:
        raise ValueError('stage0 must not execute models')
    return data


def prediction_class(envelope: dict[str, Any]) -> str:
    contract.validate_envelope(envelope)
    if envelope['task'] != 'EVIDENCE_ROUTING':
        raise ValueError('routing benchmark result cannot use drift task')
    if envelope['outcome'] == 'DECISION':
        return envelope['decision']
    if envelope['outcome'] == 'NO_CALL':
        return 'NO_CALL'
    if envelope['outcome'] == 'ERROR':
        return 'ERROR'
    raise ValueError('routing benchmark result has incompatible outcome')


def validate_probabilities(value: Any) -> dict[str, float] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != set(CLASSES):
        raise ValueError('class_probabilities must contain four routing classes')
    probs = {}
    for label in CLASSES:
        score = value[label]
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError('probability must be numeric')
        score = float(score)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError('probability outside [0,1]')
        probs[label] = score
    if abs(sum(probs.values()) - 1.0) > 1e-6:
        raise ValueError('probabilities not normalized')
    return probs


def validate_serialization(value: Any) -> None:
    required = {
        'adapter_kind',
        'adapter_revision',
        'no_call_encoding',
        'input_sha256',
        'request_sha256',
        'response_sha256',
        'runtime_identity',
        'model_identity',
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError('provider_serialization shape invalid')
    for key in ('adapter_kind', 'adapter_revision', 'no_call_encoding', 'runtime_identity', 'model_identity'):
        if not isinstance(value[key], str) or not value[key]:
            raise ValueError(f'provider_serialization {key} invalid')
    for key in ('input_sha256', 'request_sha256', 'response_sha256'):
        digest = value[key]
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f'provider_serialization {key} invalid')
        int(digest, 16)


def validate_result_rows(
    rows: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    candidate_id: str,
    expected_execution_scope: str | None = None,
) -> list[dict[str, Any]]:
    expected_ids = {row.get('case_id', row.get('id')) for row in cases}
    case_queries = {
        row.get('case_id', row.get('id')): row['query']
        for row in cases
    }
    seen = set()
    normalized = []
    for row in rows:
        required = {
            'schema',
            'case_id',
            'candidate_id',
            'execution_scope',
            'prediction',
            'class_probabilities',
            'latency_ms',
            'resource_receipt_ref',
            'provider_serialization',
        }
        if set(row) != required:
            raise ValueError('result row shape invalid')
        if row['schema'] != 'theseus.typed-decision-benchmark-result.v1':
            raise ValueError('result schema mismatch')
        if row['candidate_id'] != candidate_id:
            raise ValueError('candidate id mismatch')
        if row['execution_scope'] not in {'LOCAL_REPRODUCIBLE', 'EXTERNAL_PROVIDER'}:
            raise ValueError('execution scope invalid')
        if (
            expected_execution_scope is not None
            and row['execution_scope'] != expected_execution_scope
        ):
            raise ValueError('execution scope does not match candidate registry')
        case_id = row['case_id']
        if case_id not in expected_ids or case_id in seen:
            raise ValueError('result case id missing, unknown, or duplicate')
        seen.add(case_id)
        predicted = prediction_class(row['prediction'])
        probs = validate_probabilities(row['class_probabilities'])
        latency = row['latency_ms']
        if latency is not None:
            if isinstance(latency, bool) or not isinstance(latency, (int, float)) or latency < 0:
                raise ValueError('latency invalid')
        ref = row['resource_receipt_ref']
        if ref is not None and (not isinstance(ref, str) or not ref):
            raise ValueError('resource receipt ref invalid')
        validate_serialization(row['provider_serialization'])
        input_sha256 = hashlib.sha256(
            case_queries[case_id].encode('utf-8')
        ).hexdigest()
        if row['provider_serialization']['input_sha256'] != input_sha256:
            raise ValueError('provider serialization input hash mismatch')
        normalized.append({**row, '_prediction_class': predicted, '_probs': probs})
    if seen != expected_ids:
        raise ValueError('result coverage incomplete')
    return normalized


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def score(
    cases: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    expected = {
        row.get('case_id', row.get('id')): row['expected']
        for row in cases
    }
    confusion = {
        label: {prediction: 0 for prediction in PREDICTIONS}
        for label in CLASSES
    }
    correct = 0
    false_ready = 0
    false_probe = 0
    unknown_predicted = 0
    unknown_correct = 0
    unknown_expected = sum(value == 'UNKNOWN' for value in expected.values())
    negative_expected = sum(value == 'NO_CALL' for value in expected.values())
    negative_correct = 0
    errors = 0
    escalations = 0
    latencies = []
    brier_values = []

    for row in results:
        truth = expected[row['case_id']]
        pred = row['_prediction_class']
        confusion[truth][pred] += 1
        if pred == truth:
            correct += 1
        if pred == 'READY' and truth != 'READY':
            false_ready += 1
        if pred == 'PROBE' and truth != 'PROBE':
            false_probe += 1
        if pred == 'UNKNOWN':
            unknown_predicted += 1
            if truth == 'UNKNOWN':
                unknown_correct += 1
        if truth == 'NO_CALL' and pred == 'NO_CALL':
            negative_correct += 1
        if pred == 'ERROR':
            errors += 1
        if pred in {'PROBE', 'UNKNOWN'}:
            escalations += 1
        if row['latency_ms'] is not None:
            latencies.append(float(row['latency_ms']))
        probs = row['_probs']
        if probs is not None:
            brier_values.append(
                sum(
                    (probs[label] - (1.0 if truth == label else 0.0)) ** 2
                    for label in CLASSES
                )
            )

    n = len(results)
    non_ready = sum(value != 'READY' for value in expected.values())
    non_probe = sum(value != 'PROBE' for value in expected.values())
    return {
        'n': n,
        'exact_accuracy': ratio(correct, n),
        'confusion_matrix': confusion,
        'unknown_precision': ratio(unknown_correct, unknown_predicted),
        'unknown_recall': ratio(unknown_correct, unknown_expected),
        'false_ready_rate': ratio(false_ready, non_ready),
        'false_probe_rate': ratio(false_probe, non_probe),
        'negative_control_no_call_rate': ratio(negative_correct, negative_expected),
        'contract_error_rate': ratio(errors, n),
        'escalation_frequency': ratio(escalations, n),
        'mean_latency_ms': ratio(sum(latencies), len(latencies)),
        'calibration_n': len(brier_values),
        'multiclass_brier': ratio(sum(brier_values), len(brier_values)),
        'authority_claim': False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)

    validate = sub.add_parser('validate')
    validate.add_argument('--manifest', default=str(DEFAULT_MANIFEST))

    score_cmd = sub.add_parser('score')
    score_cmd.add_argument('--manifest', default=str(DEFAULT_MANIFEST))
    score_cmd.add_argument('--suite', choices=('primary', 'legacy'), default='primary')
    score_cmd.add_argument('--candidate-id', required=True)
    score_cmd.add_argument('--results', type=Path, required=True)

    args = parser.parse_args()
    manifest = validate_manifest(Path(args.manifest))
    if args.command == 'validate':
        print('TYPED_DECISION_BENCHMARK_PASS stage=design_only primary=24 legacy=24')
        return

    suite_spec = (
        manifest['primary_suite']
        if args.suite == 'primary'
        else manifest['legacy_compat_suite']
    )
    cases = validate_cases(
        ROOT / suite_spec['path'],
        primary=args.suite == 'primary',
    )
    registry = validate_candidates(ROOT / manifest['candidate_registry']['path'])
    if args.candidate_id not in registry['candidates']:
        raise ValueError('candidate not registered')
    candidate = registry['candidates'][args.candidate_id]
    rows = validate_result_rows(
        read_jsonl(args.results),
        cases,
        args.candidate_id,
        candidate['execution_scope'],
    )
    print(json.dumps(score(cases, rows), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
