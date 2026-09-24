import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import typed_decision_benchmark as benchmark


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'experiments' / 'typed-decision-benchmark' / 'v1' / 'manifest.json'


def digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class TypedDecisionBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = benchmark.validate_manifest(MANIFEST)
        cls.primary = benchmark.validate_cases(
            ROOT / cls.manifest['primary_suite']['path'],
            primary=True,
        )

    def _envelope(self, label):
        base = {
            'schema': 'theseus.typed-decision.v1',
            'task': 'EVIDENCE_ROUTING',
            'outcome': 'DECISION',
            'decision': label,
            'probe': None,
            'signal': None,
            'error': None,
            'advisory_confidence': {
                'kind': 'UNAVAILABLE',
                'value': None,
                'calibrated': False,
            },
            'evidence_refs': [],
            'currentness_refs': [],
            'escalation_reason': 'NONE',
            'authority_required': False,
            'extensions': {},
        }
        if label == 'PROBE':
            base['probe'] = {
                'kind': 'BENCHMARK_PROJECTION',
                'route_target': None,
            }
            base['escalation_reason'] = 'CURRENTNESS_REQUIRED'
        elif label == 'UNKNOWN':
            base['escalation_reason'] = 'INSUFFICIENT_EVIDENCE'
        elif label == 'NO_CALL':
            base['outcome'] = 'NO_CALL'
            base['decision'] = None
            base['escalation_reason'] = 'OUT_OF_SCOPE'
        elif label == 'ERROR':
            base['outcome'] = 'ERROR'
            base['decision'] = None
            base['error'] = {
                'code': 'INVALID_MODEL_OUTPUT',
                'phase': 'PARSE',
                'message': None,
            }
            base['escalation_reason'] = 'ERROR'
        return base

    def _row(self, case, label=None):
        prediction = label or case['expected']
        serial = {
            'adapter_kind': 'TEST',
            'adapter_revision': 'test-v1',
            'no_call_encoding': 'EXPLICIT_CLASS',
            'input_sha256': digest(case['query']),
            'request_sha256': digest('request:' + case['case_id']),
            'response_sha256': digest('response:' + case['case_id']),
            'runtime_identity': 'test-runtime',
            'model_identity': 'test-model',
        }
        probs = {value: 0.0 for value in benchmark.CLASSES}
        if prediction in probs:
            probs[prediction] = 1.0
        else:
            probs = None
        return {
            'schema': 'theseus.typed-decision-benchmark-result.v1',
            'case_id': case['case_id'],
            'candidate_id': 'heuristic_v1',
            'execution_scope': 'LOCAL_REPRODUCIBLE',
            'prediction': self._envelope(prediction),
            'class_probabilities': probs,
            'latency_ms': 1.0,
            'resource_receipt_ref': None,
            'provider_serialization': serial,
        }

    def test_manifest_is_design_only_and_hash_bound(self):
        self.assertFalse(self.manifest['run_policy']['stage0_executes_models'])
        self.assertEqual(self.manifest['primary_suite']['rows'], 24)
        self.assertEqual(self.manifest['legacy_compat_suite']['rows'], 24)

    def test_primary_is_balanced_and_verbatim_disjoint(self):
        counts = {}
        for row in self.primary:
            counts[row['expected']] = counts.get(row['expected'], 0) + 1
        self.assertEqual(counts, {label: 6 for label in benchmark.CLASSES})

    def test_candidate_registry_preserves_blocked_and_access_states(self):
        registry = benchmark.validate_candidates(
            ROOT / self.manifest['candidate_registry']['path']
        )['candidates']
        self.assertEqual(registry['nanojev']['status'], 'BLOCKED_STANDARD_CPU')
        self.assertEqual(registry['jev_system_one']['status'], 'ACCESS_REQUIRED')
        self.assertEqual(
            registry['nimble_open_reference']['status'],
            'CURRENTNESS_PROBE_REQUIRED',
        )
        self.assertEqual(
            registry['needle_tuned_existing']['status'],
            'ARTIFACT_SELECTION_REQUIRED',
        )

    def test_perfect_normalized_results_score_perfectly(self):
        rows = [self._row(case) for case in self.primary]
        normalized = benchmark.validate_result_rows(
            rows,
            self.primary,
            'heuristic_v1',
        )
        score = benchmark.score(self.primary, normalized)
        self.assertEqual(score['exact_accuracy'], 1.0)
        self.assertEqual(score['false_ready_rate'], 0.0)
        self.assertEqual(score['false_probe_rate'], 0.0)
        self.assertEqual(score['unknown_precision'], 1.0)
        self.assertEqual(score['unknown_recall'], 1.0)
        self.assertEqual(score['negative_control_no_call_rate'], 1.0)
        self.assertEqual(score['contract_error_rate'], 0.0)
        self.assertEqual(score['calibration_n'], 24)
        self.assertEqual(score['multiclass_brier'], 0.0)
        self.assertFalse(score['authority_claim'])

    def test_invalid_output_is_error_not_no_call_or_unknown(self):
        rows = [self._row(case) for case in self.primary]
        rows[0] = self._row(self.primary[0], 'ERROR')
        normalized = benchmark.validate_result_rows(
            rows,
            self.primary,
            'heuristic_v1',
        )
        score = benchmark.score(self.primary, normalized)
        self.assertEqual(score['contract_error_rate'], 1 / 24)
        self.assertNotEqual(score['exact_accuracy'], 1.0)

    def test_drift_result_is_rejected_from_routing_benchmark(self):
        row = self._row(self.primary[0])
        row['prediction'] = {
            **row['prediction'],
            'task': 'DRIFT_SENTINEL',
            'outcome': 'SIGNAL',
            'decision': None,
            'probe': None,
            'signal': {'name': 'X', 'payload': {}},
            'escalation_reason': 'DRIFT_SIGNAL',
        }
        with self.assertRaisesRegex(ValueError, 'routing benchmark'):
            benchmark.validate_result_rows(
                [row] + [self._row(case) for case in self.primary[1:]],
                self.primary,
                'heuristic_v1',
            )

    def test_result_input_hash_is_bound_to_exact_case_query(self):
        rows = [self._row(case) for case in self.primary]
        rows[0]['provider_serialization']['input_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'input hash mismatch'):
            benchmark.validate_result_rows(
                rows,
                self.primary,
                'heuristic_v1',
            )

    def test_execution_scope_must_match_candidate_registry(self):
        rows = [self._row(case) for case in self.primary]
        rows[0]['execution_scope'] = 'EXTERNAL_PROVIDER'
        with self.assertRaisesRegex(ValueError, 'execution scope does not match'):
            benchmark.validate_result_rows(
                rows,
                self.primary,
                'heuristic_v1',
                'LOCAL_REPRODUCIBLE',
            )

    def test_incomplete_result_coverage_fails_closed(self):
        rows = [self._row(case) for case in self.primary[:-1]]
        with self.assertRaisesRegex(ValueError, 'coverage incomplete'):
            benchmark.validate_result_rows(
                rows,
                self.primary,
                'heuristic_v1',
            )


if __name__ == '__main__':
    unittest.main()
