#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import validate_typed_decision_contract as contract

DIR = ROOT / 'experiments' / 'typed-decision-benchmark' / 'v1'
DEFAULT_MANIFEST = DIR / 'manifest.json'
CLASSES = ('PROBE', 'READY', 'UNKNOWN', 'NO_CALL')
PREDICTIONS = (*CLASSES, 'ERROR')
SHA64_RE = re.compile(r'^[0-9a-f]{64}$')
READY_STATUS = 'BENCHMARK_READY'

OPTION_DESCRIPTIONS = {
    'PROBE': 'Current verification is required and safely possible.',
    'READY': 'Current authoritative evidence already verifies the requested state.',
    'UNKNOWN': 'Evidence is insufficient and no safe or sufficient current probe is available.',
    'NO_CALL': 'The evidence-routing task is not applicable to this request.',
}
SHARED_STATE = (
    'Classify each request under the Theseus typed decision contract. '
    'Choose exactly one of PROBE, READY, UNKNOWN, or NO_CALL.'
)

def fail(message: str) -> None:
    raise ValueError(message)

def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')

def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def query_sha256(query: str) -> str:
    return hashlib.sha256(query.encode('utf-8')).hexdigest()

def require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA64_RE.fullmatch(value) is None:
        fail(f'{label} must be exactly 64 lowercase hex characters')
    return value

def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        fail(f'expected JSON object: {path}')
    return value

def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            fail(f'non-object JSONL row: {path}')
        rows.append(value)
    return rows

def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf-8')

def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n' for row in rows), encoding='utf-8')

def load_cases(path: Path, *, primary: bool) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    if len(rows) != 24:
        fail(f'expected 24 cases, observed {len(rows)}')
    ids = []
    queries = []
    labels = []
    for row in rows:
        case_id = row.get('case_id', row.get('id'))
        query = row.get('query')
        expected = row.get('expected')
        if not isinstance(case_id, str) or not case_id:
            fail('case id missing')
        if not isinstance(query, str) or not query:
            fail(f'query missing: {case_id}')
        if expected not in CLASSES:
            fail(f'expected class invalid: {case_id}')
        if primary and row.get('source_kind') != 'project_synthetic_primary_v1':
            fail(f'primary source_kind invalid: {case_id}')
        if primary and (not isinstance(row.get('family'), str) or not row['family']):
            fail(f'primary family missing: {case_id}')
        ids.append(case_id); queries.append(query); labels.append(expected)
    if len(ids) != len(set(ids)):
        fail('duplicate case id')
    if len(queries) != len(set(queries)):
        fail('duplicate query')
    if collections.Counter(labels) != collections.Counter({label: 6 for label in CLASSES}):
        fail(f'unbalanced primary labels: {collections.Counter(labels)}')
    return rows

def load_registry(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if data.get('schema') != 'theseus.typed-decision-benchmark-candidates.v1':
        fail('candidate registry schema mismatch')
    candidates = data.get('candidates')
    if not isinstance(candidates, dict) or not candidates:
        fail('candidate registry missing')
    for candidate_id, item in candidates.items():
        if not isinstance(item, dict):
            fail(f'candidate invalid: {candidate_id}')
        if item.get('status') not in {
            'BENCHMARK_READY', 'BLOCKED_STANDARD_CPU', 'ACCESS_REQUIRED',
            'CURRENTNESS_PROBE_REQUIRED', 'DEFERRED_FOR_V1'
        }:
            fail(f'candidate status invalid: {candidate_id}')
        if item.get('execution_scope') not in {'LOCAL_REPRODUCIBLE', 'EXTERNAL_PROVIDER'}:
            fail(f'execution scope invalid: {candidate_id}')
        adapter = item.get('adapter')
        if not isinstance(adapter, dict) or set(adapter) != {'kind', 'revision', 'no_call_encoding'}:
            fail(f'adapter identity invalid: {candidate_id}')
        if not isinstance(item.get('runtime_identity'), dict) or not item['runtime_identity']:
            fail(f'runtime identity missing: {candidate_id}')
        if not isinstance(item.get('model_identity'), dict) or not item['model_identity']:
            fail(f'model identity missing: {candidate_id}')
    return data

def validate_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    data = load_json(path)
    if data.get('schema') != 'theseus.typed-decision-benchmark-manifest.v1':
        fail('manifest schema mismatch')
    if data.get('task') != 'EVIDENCE_ROUTING':
        fail('v1 benchmark must be EVIDENCE_ROUTING')
    for key in ('contract', 'primary_suite', 'legacy_compat_suite', 'baseline', 'candidate_registry'):
        spec = data.get(key)
        if not isinstance(spec, dict):
            fail(f'manifest section missing: {key}')
        target = ROOT / spec['path']
        if sha256_file(target) != require_sha256(spec['sha256'], f'{key}.sha256'):
            fail(f'{key} digest mismatch')
    primary = load_cases(ROOT / data['primary_suite']['path'], primary=True)
    legacy = load_cases(ROOT / data['legacy_compat_suite']['path'], primary=False)
    if set(row['query'] for row in primary) & set(row['query'] for row in legacy):
        fail('primary query overlaps legacy suite verbatim')
    registry = load_registry(ROOT / data['candidate_registry']['path'])
    planned = data.get('included_candidates')
    if planned != ['baseline_constant_unknown', 'needle3_base', 'semif_qwen3_0_6b_q8', 'kev_0_8b']:
        fail('included candidate matrix drifted')
    for candidate_id in planned:
        if registry['candidates'][candidate_id]['status'] != READY_STATUS:
            fail(f'included candidate not benchmark ready: {candidate_id}')
    if data.get('qa_executes_models') is not False:
        fail('QA must not execute candidate models')
    return data

def envelope_for(label: str, *, error_code: str = 'INVALID_MODEL_OUTPUT') -> dict[str, Any]:
    base = {
        'schema': 'theseus.typed-decision.v1', 'task': 'EVIDENCE_ROUTING',
        'outcome': 'DECISION', 'decision': label, 'probe': None, 'signal': None, 'error': None,
        'advisory_confidence': {'kind': 'UNAVAILABLE', 'value': None, 'calibrated': False},
        'evidence_refs': [], 'currentness_refs': [], 'escalation_reason': 'NONE',
        'authority_required': False, 'extensions': {},
    }
    if label == 'PROBE':
        base['probe'] = {'kind': 'BENCHMARK_PROJECTION', 'route_target': None}
        base['escalation_reason'] = 'CURRENTNESS_REQUIRED'
    elif label == 'UNKNOWN':
        base['escalation_reason'] = 'INSUFFICIENT_EVIDENCE'
    elif label == 'NO_CALL':
        base['outcome'] = 'NO_CALL'; base['decision'] = None; base['escalation_reason'] = 'OUT_OF_SCOPE'
    elif label == 'ERROR':
        base['outcome'] = 'ERROR'; base['decision'] = None
        base['error'] = {'code': error_code, 'phase': 'PARSE', 'message': None}
        base['escalation_reason'] = 'ERROR'
    elif label != 'READY':
        fail(f'unknown label: {label}')
    contract.validate_envelope(base)
    return base

def prediction_class(envelope: dict[str, Any]) -> str:
    contract.validate_envelope(envelope)
    if envelope['task'] != 'EVIDENCE_ROUTING':
        fail('routing benchmark cannot accept drift task')
    if envelope['outcome'] == 'DECISION': return envelope['decision']
    if envelope['outcome'] == 'NO_CALL': return 'NO_CALL'
    if envelope['outcome'] == 'ERROR': return 'ERROR'
    fail('routing benchmark outcome invalid')

def normalized_choice(probabilities: dict[str, float]) -> str:
    best = max(probabilities.values())
    winners = [label for label in CLASSES if probabilities[label] == best]
    return winners[0] if len(winners) == 1 else 'ERROR'

def validate_probabilities(value: Any) -> dict[str, float] | None:
    if value is None: return None
    if not isinstance(value, dict) or set(value) != set(CLASSES):
        fail('class_probabilities must contain exactly four routing classes')
    result = {}
    for label in CLASSES:
        score = value[label]
        if isinstance(score, bool) or not isinstance(score, (int, float)): fail('probability must be numeric')
        score = float(score)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0: fail('probability outside [0,1]')
        result[label] = score
    if not math.isclose(sum(result.values()), 1.0, rel_tol=0.0, abs_tol=1e-6):
        fail('probabilities not normalized')
    return result

def validate_result_rows(rows: list[dict[str, Any]], cases: list[dict[str, Any]], candidate_id: str, registry: dict[str, Any]) -> list[dict[str, Any]]:
    candidate = registry['candidates'].get(candidate_id)
    if not isinstance(candidate, dict): fail('candidate not registered')
    if candidate.get('status') != READY_STATUS:
        fail(f'candidate is not benchmark ready: {candidate_id}')
    expected_ids = [row.get('case_id', row.get('id')) for row in cases]
    case_by_id = {row.get('case_id', row.get('id')): row for row in cases}
    seen = []
    normalized = []
    required = {'schema','case_id','candidate_id','execution_scope','prediction','class_probabilities','latency_ms','resource_receipt_ref','provider_serialization'}
    serial_required = {'adapter_kind','adapter_revision','no_call_encoding','input_sha256','request_sha256','response_sha256','runtime_identity','model_identity'}
    for row in rows:
        if set(row) != required: fail('result row shape invalid')
        if row['schema'] != 'theseus.typed-decision-benchmark-result.v1': fail('result schema mismatch')
        if row['candidate_id'] != candidate_id: fail('candidate id mismatch')
        if row['execution_scope'] != candidate['execution_scope']: fail('execution scope does not match candidate registry')
        case_id = row['case_id']
        if case_id not in case_by_id or case_id in seen: fail('result case id missing, unknown, or duplicate')
        seen.append(case_id)
        serial = row['provider_serialization']
        if not isinstance(serial, dict) or set(serial) != serial_required: fail('provider_serialization shape invalid')
        adapter = candidate['adapter']
        if serial['adapter_kind'] != adapter['kind'] or serial['adapter_revision'] != adapter['revision'] or serial['no_call_encoding'] != adapter['no_call_encoding']:
            fail('adapter identity does not match candidate registry')
        if serial['runtime_identity'] != candidate['runtime_identity']: fail('runtime identity does not match candidate registry')
        if serial['model_identity'] != candidate['model_identity']: fail('model identity does not match candidate registry')
        if serial['input_sha256'] != query_sha256(case_by_id[case_id]['query']): fail('provider serialization input hash mismatch')
        require_sha256(serial['request_sha256'], 'request_sha256'); require_sha256(serial['response_sha256'], 'response_sha256')
        latency = row['latency_ms']
        if latency is not None:
            if isinstance(latency, bool) or not isinstance(latency, (int, float)) or not math.isfinite(float(latency)) or float(latency) < 0:
                fail('latency must be finite and nonnegative')
        pred = prediction_class(row['prediction'])
        probs = validate_probabilities(row['class_probabilities'])
        normalized.append({**row, '_prediction_class': pred, '_probs': probs})
    if seen != expected_ids: fail('result coverage or order incomplete')
    return normalized

def build_result(case: dict[str, Any], candidate_id: str, candidate: dict[str, Any], label: str, request: Any, response: Any, *, probabilities: dict[str, float] | None, latency_ms: float | None, resource_receipt_ref: str | None) -> dict[str, Any]:
    return {
        'schema': 'theseus.typed-decision-benchmark-result.v1',
        'case_id': case['case_id'], 'candidate_id': candidate_id, 'execution_scope': candidate['execution_scope'],
        'prediction': envelope_for(label), 'class_probabilities': probabilities, 'latency_ms': latency_ms,
        'resource_receipt_ref': resource_receipt_ref,
        'provider_serialization': {
            'adapter_kind': candidate['adapter']['kind'], 'adapter_revision': candidate['adapter']['revision'],
            'no_call_encoding': candidate['adapter']['no_call_encoding'], 'input_sha256': query_sha256(case['query']),
            'request_sha256': canonical_sha256(request), 'response_sha256': canonical_sha256(response),
            'runtime_identity': candidate['runtime_identity'], 'model_identity': candidate['model_identity'],
        },
    }

def semif_row(case: dict[str, Any]) -> dict[str, Any]:
    return {'id': case['case_id'], 'state': SHARED_STATE, 'question': case['query'], 'options': [{'id': label, 'description': OPTION_DESCRIPTIONS[label]} for label in CLASSES]}

def kev_fixture(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        'state': SHARED_STATE,
        'questions': [{'instr': case['query'], 'options': [OPTION_DESCRIPTIONS[label] for label in CLASSES], 'label': 0} for case in cases],
        '_theseus': {'label_semantics': 'DUMMY_REQUIRED_BY_KEV_ENCODER_NOT_EXPECTED_TARGET', 'option_ids': list(CLASSES)},
    }

def score(cases: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    expected = {row['case_id']: row['expected'] for row in cases}
    confusion = {truth: {pred: 0 for pred in PREDICTIONS} for truth in CLASSES}
    correct=false_ready=false_probe=unknown_pred=unknown_correct=negative_correct=errors=escalations=0
    latencies=[]; brier=[]
    for row in results:
        truth=expected[row['case_id']]; pred=row['_prediction_class']; confusion[truth][pred]+=1
        correct += int(pred==truth); false_ready += int(pred=='READY' and truth!='READY'); false_probe += int(pred=='PROBE' and truth!='PROBE')
        unknown_pred += int(pred=='UNKNOWN'); unknown_correct += int(pred=='UNKNOWN' and truth=='UNKNOWN'); negative_correct += int(truth=='NO_CALL' and pred=='NO_CALL')
        errors += int(pred=='ERROR'); escalations += int(pred in {'PROBE','UNKNOWN'})
        if row['latency_ms'] is not None: latencies.append(float(row['latency_ms']))
        probs=row['_probs']
        if probs is not None: brier.append(sum((probs[label]-(1.0 if truth==label else 0.0))**2 for label in CLASSES))
    n=len(results)
    ratio=lambda a,b: a/b if b else None
    return {
        'n': n, 'exact_accuracy': ratio(correct,n), 'confusion_matrix': confusion,
        'unknown_precision': ratio(unknown_correct,unknown_pred), 'unknown_recall': ratio(unknown_correct,sum(v=='UNKNOWN' for v in expected.values())),
        'false_ready_rate': ratio(false_ready,sum(v!='READY' for v in expected.values())), 'false_probe_rate': ratio(false_probe,sum(v!='PROBE' for v in expected.values())),
        'negative_control_no_call_rate': ratio(negative_correct,sum(v=='NO_CALL' for v in expected.values())), 'contract_error_rate': ratio(errors,n),
        'escalation_frequency': ratio(escalations,n), 'mean_latency_ms': ratio(sum(latencies),len(latencies)),
        'calibration_n': len(brier), 'multiclass_brier': ratio(sum(brier),len(brier)), 'authority_claim': False,
    }

def main() -> None:
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest='command',required=True)
    validate=sub.add_parser('validate'); validate.add_argument('--manifest',default=str(DEFAULT_MANIFEST))
    ps=sub.add_parser('prepare-semif'); ps.add_argument('--out',type=Path,required=True)
    pk=sub.add_parser('prepare-kev'); pk.add_argument('--out',type=Path,required=True)
    rb=sub.add_parser('run-baseline'); rb.add_argument('--out',type=Path,required=True)
    sc=sub.add_parser('score'); sc.add_argument('--candidate-id',required=True); sc.add_argument('--results',type=Path,required=True); sc.add_argument('--suite',choices=('primary','legacy'),default='primary'); sc.add_argument('--out',type=Path)
    args=parser.parse_args(); manifest=validate_manifest(Path(getattr(args,'manifest',DEFAULT_MANIFEST)))
    cases=load_cases(ROOT/manifest['primary_suite']['path'],primary=True)
    registry=load_registry(ROOT/manifest['candidate_registry']['path'])
    if args.command=='validate':
        print('TYPED_DECISION_BENCHMARK_PASS stage=working_design primary=24 legacy=24 models_executed=0'); return
    if args.command=='prepare-semif': write_jsonl(args.out,[semif_row(case) for case in cases]); return
    if args.command=='prepare-kev': write_json(args.out,kev_fixture(cases)); return
    if args.command=='run-baseline':
        candidate_id='baseline_constant_unknown'; candidate=registry['candidates'][candidate_id]
        rows=[build_result(case,candidate_id,candidate,'UNKNOWN',{'query':case['query']},{'decision':'UNKNOWN'},probabilities=None,latency_ms=0.0,resource_receipt_ref=None) for case in cases]
        write_jsonl(args.out,rows); return
    suite=cases if args.suite=='primary' else load_cases(ROOT/manifest['legacy_compat_suite']['path'],primary=False)
    rows=validate_result_rows(read_jsonl(args.results),suite,args.candidate_id,registry); report=score(suite,rows)
    if args.out: write_json(args.out,report)
    else: print(json.dumps(report,indent=2,sort_keys=True))

if __name__ == '__main__':
    main()
