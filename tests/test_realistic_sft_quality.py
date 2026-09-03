import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class RealisticSftQualityEvalContractTest(unittest.TestCase):
    def test_loader_binds_projection_rows_to_semantic_case_ids_without_changing_behavioral_inputs(self):
        from scripts.run_realistic_sft_eval import load_bound_cases

        train = load_bound_cases(
            ROOT / 'experiments/needle-realistic-sft/data/train.needle.jsonl',
            ROOT / 'experiments/needle-realistic-sft/source/semantic-cases.jsonl',
            'train',
        )
        heldout = load_bound_cases(
            ROOT / 'experiments/needle-realistic-sft/data/heldout.eval.jsonl',
            ROOT / 'experiments/needle-realistic-sft/source/semantic-cases.jsonl',
            'heldout',
        )
        self.assertEqual(len(train), 360)
        self.assertEqual(len(heldout), 96)
        self.assertEqual(len({row['id'] for row in train + heldout}), 456)
        first = train[0]
        self.assertEqual(first['query'], 'Use route to classify the following evidence:\n\nCached information about runtime-alpha is stale, and a harmless current version query is available.')
        contract = json.loads((ROOT / 'experiments/needle-realistic-sft/contract/route-schema.json').read_text())
        self.assertEqual(first['tools'], [contract])
        self.assertEqual(first['expected'], 'PROBE')
        self.assertEqual(first['category'], 'train_positive')
        negative = next(row for row in train if row['expected'] == 'NO_CALL')
        self.assertEqual(negative['category'], 'train_negative')

    def test_loader_rejects_projection_semantic_order_mismatch(self):
        from scripts.run_realistic_sft_eval import load_bound_cases

        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            projection = td / 'p.jsonl'
            semantic = td / 's.jsonl'
            projection.write_text(json.dumps({'query':'WRONG','tools':[{'name':'route'}],'answers':[]})+'\n')
            semantic.write_text(json.dumps({
                'case_id':'heldout-x','split':'heldout','applicability':'none','expected_decision':None,
                'query':'expected query','family_id':'f','semantic_rule':'x','rationale':'x',
                'derivation_family':'x','entity_variant':'x','schema_contract':'x','source_kind':'synthetic_repo_authored'
            })+'\n')
            with self.assertRaisesRegex(ValueError, 'projection/semantic query mismatch'):
                load_bound_cases(projection, semantic, 'heldout')

    def test_response_classifier_is_strict(self):
        from scripts.run_realistic_sft_eval import classify_response
        self.assertEqual(classify_response({'type':'call','function_calls':[{'name':'route','arguments':{'decision':'READY'}}]}), 'READY')
        self.assertEqual(classify_response({'type':'text'}), 'NO_CALL')
        self.assertEqual(classify_response({'type':'call','function_calls':[{'name':'other','arguments':{}}]}), 'INVALID')


if __name__ == '__main__':
    unittest.main()

class RealisticSftQualityReceiptTest(unittest.TestCase):
    @staticmethod
    def _rows(prefix, positives_correct, positive_total, route_calls, dominant_count, negative_no_call, negative_total):
        rows=[]
        # Positive cases: first positives_correct are correct READY, then wrong UNKNOWN/NO_CALL.
        for i in range(positive_total):
            expected='READY'
            if i < positives_correct:
                predicted='READY'
            elif i < route_calls:
                predicted='UNKNOWN'
            else:
                predicted='NO_CALL'
            # Force desired dominant count among valid calls by using READY for first dominant_count calls.
            if i < route_calls:
                predicted = 'READY' if i < dominant_count else ('UNKNOWN' if i % 2 else 'PROBE')
                if i < positives_correct:
                    expected=predicted
                else:
                    expected='READY' if predicted != 'READY' else 'UNKNOWN'
            rows.append({'id':f'{prefix}-p{i}','category':f'{prefix}_positive','expected':expected,'predicted':predicted,'correct':predicted==expected})
        for i in range(negative_total):
            predicted='NO_CALL' if i < negative_no_call else 'READY'
            rows.append({'id':f'{prefix}-n{i}','category':f'{prefix}_negative','expected':'NO_CALL','predicted':predicted,'correct':predicted=='NO_CALL'})
        return rows

    def test_replica_acceptance_uses_preregistered_train_heldout_and_applicability_thresholds(self):
        from scripts.realistic_sft_quality_receipt import evaluate_replica
        base_train=self._rows('train',150,300,250,150,50,60)
        tuned_train=self._rows('train',240,300,280,160,56,60)
        base_held=self._rows('heldout',30,72,60,36,20,24)
        tuned_held=self._rows('heldout',40,72,60,40,20,24)
        result=evaluate_replica(base_train,tuned_train,base_held,tuned_held)
        self.assertTrue(result['train_fit'])
        self.assertTrue(result['heldout_positive_gain_ok'])
        self.assertTrue(result['heldout_reachability_ok'])
        self.assertTrue(result['heldout_negative_no_call_ok'])
        self.assertTrue(result['dominant_decision_ok'])
        self.assertTrue(result['learned_and_generalizes'])

    def test_final_disposition_requires_both_replicas(self):
        from scripts.realistic_sft_quality_receipt import final_disposition
        good={'train_fit':True,'learned_and_generalizes':True,'applicability_regression':False}
        gap={'train_fit':True,'learned_and_generalizes':False,'applicability_regression':False}
        under={'train_fit':False,'learned_and_generalizes':False,'applicability_regression':False}
        reg={'train_fit':True,'learned_and_generalizes':False,'applicability_regression':True}
        self.assertEqual(final_disposition(good,good),'ACCEPTED_LEARNED_AND_GENERALIZES')
        self.assertEqual(final_disposition(good,gap),'INCONCLUSIVE_REPLICA_DIVERGENCE')
        self.assertEqual(final_disposition(gap,gap),'INCONCLUSIVE_TRAIN_FIT_GENERALIZATION_GAP')
        self.assertEqual(final_disposition(under,under),'REJECTED_PERSISTENT_UNDERFIT')
        self.assertEqual(final_disposition(reg,gap),'REJECTED_APPLICABILITY_REGRESSION')
