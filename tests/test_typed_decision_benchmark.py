import copy
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

from scripts import typed_decision_benchmark as bench

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'experiments'/'typed-decision-benchmark'/'v1'/'manifest.json'

class TypedDecisionBenchmarkV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=bench.validate_manifest(MANIFEST)
        cls.primary=bench.load_cases(ROOT/cls.manifest['primary_suite']['path'],primary=True)
        cls.registry=bench.load_registry(ROOT/cls.manifest['candidate_registry']['path'])

    def test_preregistered_hashes_are_exact(self):
        self.assertEqual(bench.sha256_file(ROOT/self.manifest['primary_suite']['path']),'1cef5f9702d7dc2f4e418e604be69fc084327df57f4fd017129ecf9fcd87e8de')
        self.assertEqual(bench.sha256_file(ROOT/self.manifest['legacy_compat_suite']['path']),'05992ce1354cf7b4090eeabf23363e4bb455673c93cfed768814b8ecb1118034')
        self.assertEqual(bench.sha256_file(ROOT/self.manifest['baseline']['path']),'831858cc16b17f7eb49326549d37d9453cdba45cc4cb220b434b6a92213623a0')

    def test_semif_native_input_contains_no_expected_label(self):
        rows=[bench.semif_row(case) for case in self.primary]
        payload=json.dumps(rows,sort_keys=True)
        self.assertNotIn('"expected"',payload)
        for row in rows:
            self.assertEqual([o['id'] for o in row['options']],list(bench.CLASSES))

    def test_kev_uses_constant_dummy_label_not_expected_target(self):
        fixture=bench.kev_fixture(self.primary)
        self.assertEqual(fixture['_theseus']['label_semantics'],'DUMMY_REQUIRED_BY_KEV_ENCODER_NOT_EXPECTED_TARGET')
        self.assertEqual({q['label'] for q in fixture['questions']},{0})
        self.assertNotIn('expected',fixture)

    def _valid_rows(self,candidate_id='baseline_constant_unknown'):
        candidate=self.registry['candidates'][candidate_id]
        return [bench.build_result(case,candidate_id,candidate,case['expected'],{'query':case['query']},{'prediction':case['expected']},probabilities={label:(1.0 if label==case['expected'] else 0.0) for label in bench.CLASSES},latency_ms=1.0,resource_receipt_ref=None) for case in self.primary]

    def test_non_ready_candidate_cannot_be_scored(self):
        with self.assertRaisesRegex(ValueError,'not benchmark ready'):
            bench.validate_result_rows([],self.primary,'nanojev',self.registry)

    def test_runtime_identity_must_exact_match_registry(self):
        rows=self._valid_rows(); rows[0]['provider_serialization']['runtime_identity']={'tampered':True}
        with self.assertRaisesRegex(ValueError,'runtime identity'): bench.validate_result_rows(rows,self.primary,'baseline_constant_unknown',self.registry)

    def test_latency_must_be_finite(self):
        rows=self._valid_rows(); rows[0]['latency_ms']=float('nan')
        with self.assertRaisesRegex(ValueError,'finite'): bench.validate_result_rows(rows,self.primary,'baseline_constant_unknown',self.registry)

    def test_hashes_must_be_strict_lower_hex(self):
        rows=self._valid_rows(); rows[0]['provider_serialization']['response_sha256']='g'*64
        with self.assertRaisesRegex(ValueError,'lowercase hex'): bench.validate_result_rows(rows,self.primary,'baseline_constant_unknown',self.registry)

    def test_input_hash_is_exact_query_hash(self):
        rows=self._valid_rows(); rows[0]['provider_serialization']['input_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'input hash mismatch'): bench.validate_result_rows(rows,self.primary,'baseline_constant_unknown',self.registry)

    def test_perfect_synthetic_projection_scores_perfectly(self):
        rows=bench.validate_result_rows(self._valid_rows(),self.primary,'baseline_constant_unknown',self.registry)
        score=bench.score(self.primary,rows)
        self.assertEqual(score['exact_accuracy'],1.0); self.assertEqual(score['false_ready_rate'],0.0); self.assertEqual(score['false_probe_rate'],0.0); self.assertEqual(score['multiclass_brier'],0.0); self.assertFalse(score['authority_claim'])

    def test_exact_probability_tie_fails_closed_to_error(self):
        probs={'PROBE':0.5,'READY':0.5,'UNKNOWN':0.0,'NO_CALL':0.0}
        self.assertEqual(bench.normalized_choice(probs),'ERROR')

    def test_qa_manifest_declares_no_model_execution(self):
        self.assertFalse(self.manifest['qa_executes_models'])

if __name__=='__main__': unittest.main()
