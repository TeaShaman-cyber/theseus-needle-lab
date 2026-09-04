import unittest

from scripts.stage_c_quality_receipt import scope_metrics, evaluate_replica_pair, final_disposition


SEMANTIC={"PROBE","READY","UNKNOWN"}


def make_rows(prefix, positive_correct=36, negative_no_call=22, dominant=24, failed=False):
    rows=[]
    # 72 route-positive cases. Keep 60 observable route calls and 12 NO_CALL misses.
    for i in range(72):
        if failed and i == 0:
            predicted="ERROR"
            expected="READY"
        elif i < 60:
            if i < dominant:
                predicted="READY"
            else:
                predicted="PROBE" if i % 2 == 0 else "UNKNOWN"
            expected=predicted if i < positive_correct else ("READY" if predicted != "READY" else "UNKNOWN")
        else:
            predicted="NO_CALL"
            expected="READY"
        rows.append({"id":f"{prefix}-p{i}","category":"heldout_positive","expected":expected,"predicted":predicted,"correct":predicted==expected})
    for i in range(24):
        predicted="NO_CALL" if i < negative_no_call else "READY"
        rows.append({"id":f"{prefix}-n{i}","category":"heldout_negative","expected":"NO_CALL","predicted":predicted,"correct":predicted=="NO_CALL"})
    return rows


class StageCQualityMetricsTest(unittest.TestCase):
    def test_metrics_separate_applicability_from_semantic_decision(self):
        rows=make_rows("x",positive_correct=36,negative_no_call=22,dominant=24)
        m=scope_metrics(rows)
        self.assertEqual(m["negative_no_call"],22)
        self.assertEqual(m["positive_correct"],36)
        self.assertEqual(m["applicability_confusion"]["NONE->NONE"],22)
        self.assertEqual(m["applicability_confusion"]["NONE->ROUTE"],2)
        self.assertEqual(m["applicability_confusion"]["ROUTE->NONE"],12)
        self.assertEqual(sum(m["semantic_confusion"].values()),60)
        self.assertLessEqual(m["dominant_semantic_decision_rate"],0.70)

    def test_runtime_error_is_not_counted_as_no_call(self):
        rows=make_rows("x",failed=True)
        m=scope_metrics(rows)
        self.assertEqual(m["runtime_or_invalid"],1)
        self.assertNotIn("ROUTE->NONE", {"runtime":1})
        self.assertEqual(m["applicability_confusion"].get("ROUTE->INVALID"),1)

    def test_exact_scope_validation_rejects_duplicate_or_missing_case_ids(self):
        from scripts.stage_c_quality_receipt import validate_scope_rows
        rows=make_rows("heldout")
        expected={r["id"]:(r["category"],r["expected"]) for r in rows}
        corrupted=list(rows)
        corrupted[-1]=dict(corrupted[0])
        with self.assertRaisesRegex(ValueError,"exact case ids"):
            validate_scope_rows(corrupted,expected,"heldout")

    def test_exact_scope_validation_rejects_wrong_registered_category(self):
        from scripts.stage_c_quality_receipt import validate_scope_rows
        rows=make_rows("heldout")
        expected={r["id"]:(r["category"],r["expected"]) for r in rows}
        bad=[dict(r) for r in rows]
        bad[0]["category"]="heldout_negative"
        with self.assertRaisesRegex(ValueError,"category"):
            validate_scope_rows(bad,expected,"heldout")


class StageCReplicaAcceptanceTest(unittest.TestCase):
    def good_pair(self):
        arm_a_final=make_rows("a",positive_correct=34,negative_no_call=16,dominant=24)
        arm_b_early=make_rows("be",positive_correct=36,negative_no_call=22,dominant=24)
        arm_b_final=make_rows("bf",positive_correct=35,negative_no_call=21,dominant=24)
        return arm_a_final,arm_b_early,arm_b_final

    def test_good_recovery_passes_all_registered_gates(self):
        a,b,r=self.good_pair()
        result=evaluate_replica_pair(a,b,r)
        self.assertTrue(result["recovery_floor_ok"])
        self.assertTrue(result["positive_floor_ok"])
        self.assertTrue(result["dominant_semantic_ok"])
        self.assertTrue(result["applicability_not_collapsed"])
        self.assertTrue(result["reduced_weight_retention_ok"])
        self.assertTrue(result["paired_specificity_ok"])
        self.assertTrue(result["accepted"])
        self.assertEqual(result["arm_b_final"]["negative_no_call"],21)
        self.assertEqual(result["arm_b_early"]["negative_no_call"],22)

    def test_recovery_floor_failure_has_registered_disposition(self):
        a,b,r=self.good_pair()
        result=evaluate_replica_pair(a,b,make_rows("bfail",36,19,24))
        self.assertEqual(result["disposition"],"REJECTED_APPLICABILITY_RECOVERY_FAILED")

    def test_positive_floor_failure_has_registered_disposition(self):
        a,b,r=self.good_pair()
        result=evaluate_replica_pair(a,b,make_rows("bfail",31,22,24))
        self.assertEqual(result["disposition"],"REJECTED_POSITIVE_RETENTION_REGRESSION")

    def test_semantic_collapse_is_rejected(self):
        a,b,r=self.good_pair()
        collapsed=make_rows("bfinal",36,22,60)
        result=evaluate_replica_pair(a,b,collapsed)
        self.assertEqual(result["disposition"],"REJECTED_DECISION_COLLAPSE")

    def test_arm_b_must_beat_control_without_worse_positive_correctness(self):
        a=make_rows("a",36,22,24)
        b_early=make_rows("be",36,22,24)
        b_final=make_rows("bf",35,22,24)
        result=evaluate_replica_pair(a,b_early,b_final)
        self.assertEqual(result["disposition"],"INCONCLUSIVE_RECOVERY_SPECIFICITY")

    def test_recovery_must_survive_reduced_weight_phase(self):
        a,_,b_final=self.good_pair()
        early=make_rows("early",35,18,24)
        result=evaluate_replica_pair(a,early,b_final)
        self.assertFalse(result["reduced_weight_retention_ok"])
        self.assertEqual(result["disposition"],"REJECTED_APPLICABILITY_RECOVERY_FAILED")

    def test_final_acceptance_requires_both_replicas(self):
        a,b,r=self.good_pair()
        good=evaluate_replica_pair(a,b,r)
        bad=evaluate_replica_pair(a,b,make_rows("b2",36,19,24))
        self.assertEqual(final_disposition(good,good),"ACCEPTED_STAGE_C_APPLICABILITY_RECOVERY")
        self.assertEqual(final_disposition(good,bad),"REJECTED_APPLICABILITY_RECOVERY_FAILED")


if __name__ == '__main__':
    unittest.main()

class StageCQualityCliTest(unittest.TestCase):
    def test_replica_and_final_cli_write_receipts(self):
        import json, pathlib, subprocess, tempfile
        root=pathlib.Path(__file__).resolve().parents[1]
        td=pathlib.Path(tempfile.mkdtemp(prefix='stage-c-quality-cli-'))
        def write(name,rows):
            p=td/name
            p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            return p
        a_rows=make_rows('heldout',34,16,24)
        def with_registered_truth(candidate):
            out=[]
            for truth,row in zip(a_rows,candidate):
                x=dict(row)
                x['id']=truth['id']; x['category']=truth['category']; x['expected']=truth['expected']
                x['correct']=x['predicted']==x['expected']
                out.append(x)
            return out
        be_rows=with_registered_truth(make_rows('heldout',36,22,24))
        bf_rows=with_registered_truth(make_rows('heldout',35,21,24))
        for row in a_rows:
            row['model_id']='stage-c-A-R1-final'; row['weights_sha256']='2'*64
        for row in be_rows:
            row['model_id']='stage-c-B-R1-early'; row['weights_sha256']='3'*64
        for row in bf_rows:
            row['model_id']='stage-c-B-R1-final'; row['weights_sha256']='4'*64
        def add_state(row):
            return {
                'applicability':'NONE' if row['expected']=='NO_CALL' else 'ROUTE',
                'decision':row['expected'],
                'tool_need':'unnecessary' if row['expected']=='NO_CALL' else 'required',
                'evidence_state':'sufficient' if row['expected'] in {'NO_CALL','READY'} else 'insufficient',
                'cost_class':'low','risk_class':'low',
            }
        for row in be_rows+bf_rows:
            row['expected_state']=add_state(row); row['predicted_state']=dict(row['expected_state']); row['state_correct']=True
        ae_rows=[dict(r) for r in a_rows]
        for row in ae_rows:
            row['model_id']='stage-c-A-R1-early'; row['weights_sha256']='1'*64
        ae=write('ae.jsonl',ae_rows)
        a=write('a.jsonl',a_rows)
        be=write('be.jsonl',be_rows)
        bf=write('bf.jsonl',bf_rows)
        def train_rows(source_rows):
            out=[]
            for row in source_rows:
                x=dict(row)
                x['id']=x['id'].replace('heldout-','train-',1)
                x['category']=x['category'].replace('heldout_','train_',1)
                out.append(x)
            return out
        at_rows=train_rows(a_rows); bet_rows=train_rows(be_rows); bft_rows=train_rows(bf_rows)
        for row in at_rows:
            row['model_id']='stage-c-A-R1-final'; row['weights_sha256']='2'*64
        for row in bet_rows:
            row['model_id']='stage-c-B-R1-early'; row['weights_sha256']='3'*64
        for row in bft_rows:
            row['model_id']='stage-c-B-R1-final'; row['weights_sha256']='4'*64
        for row in bet_rows+bft_rows:
            row['expected_state']=add_state(row); row['predicted_state']=dict(row['expected_state']); row['state_correct']=True
        aet_rows=[dict(r) for r in at_rows]
        for row in aet_rows:
            row['model_id']='stage-c-A-R1-early'; row['weights_sha256']='1'*64
        aet=write('aet.jsonl',aet_rows)
        at=write('at.jsonl',at_rows); bet=write('bet.jsonl',bet_rows); bft=write('bft.jsonl',bft_rows)
        semantic=td/'semantic.jsonl'
        semantic_rows=[]
        for row in a_rows:
            semantic_rows.append({'case_id':row['id'],'split':'heldout','applicability':'none' if row['expected']=='NO_CALL' else 'route','expected_decision':None if row['expected']=='NO_CALL' else row['expected']})
        for row in at_rows:
            semantic_rows.append({'case_id':row['id'],'split':'train','applicability':'none' if row['expected']=='NO_CALL' else 'route','expected_decision':None if row['expected']=='NO_CALL' else row['expected']})
        semantic.write_text(''.join(json.dumps(r)+'\n' for r in semantic_rows))
        train_a=td/'train-a.json'; train_b=td/'train-b.json'
        import hashlib
        manifest_sha=hashlib.sha256((root/'experiments/needle-stage-c-applicability/manifests/stage-c-curriculum-manifest.json').read_bytes()).hexdigest()
        train_a.write_text(json.dumps({'schema':'theseus.needle.stage_c_train.v1','arm_id':'A','replica_id':'R1','source':{'experiment_commit':'a'*40},'inputs':{'base_checkpoint_sha256':'4b0a972d163ffc7678fb3c36bace508114872e9d2ce9e10f225825752d3795bc','curriculum_manifest_sha256':manifest_sha},'training_config':{'seed':101,'epochs':15,'batch_size':16,'lr':1e-4,'lora_rank':16,'lora_alpha':32.0,'max_len':512,'val_split':0.0},'artifacts':{'early_cact_sha256':'1'*64,'final_cact_sha256':'2'*64}}))
        train_b.write_text(json.dumps({'schema':'theseus.needle.stage_c_train.v1','arm_id':'B','replica_id':'R1','source':{'experiment_commit':'a'*40},'inputs':{'base_checkpoint_sha256':'4b0a972d163ffc7678fb3c36bace508114872e9d2ce9e10f225825752d3795bc','curriculum_manifest_sha256':manifest_sha},'training_config':{'seed':101,'epochs':15,'batch_size':16,'lr':1e-4,'lora_rank':16,'lora_alpha':32.0,'max_len':512,'val_split':0.0},'artifacts':{'early_cact_sha256':'3'*64,'final_cact_sha256':'4'*64}}))
        r1=td/'r1.json'
        cmd=['python3',str(root/'scripts/stage_c_quality_receipt.py'),'replica','--semantic',str(semantic),'--arm-a-early',str(ae),'--arm-a-early-train',str(aet),'--arm-a-final',str(a),'--arm-a-final-train',str(at),'--arm-b-early',str(be),'--arm-b-early-train',str(bet),'--arm-b-final',str(bf),'--arm-b-final-train',str(bft),'--arm-a-train-receipt',str(train_a),'--arm-b-train-receipt',str(train_b),'--replica-id','R1','--experiment-commit','a'*40,'--launcher-commit','b'*40,'--run-id','123','--output',str(r1)]
        x=subprocess.run(cmd,text=True,capture_output=True)
        self.assertEqual(x.returncode,0,x.stderr)
        receipt=json.loads(r1.read_text())
        self.assertEqual(receipt['schema'],'theseus.needle.stage_c_replica_eval.v1')
        self.assertTrue(receipt['evaluation']['accepted'])
        self.assertEqual(receipt['model_artifacts']['arm_a_early_cact_sha256'],'1'*64)
        self.assertEqual(receipt['model_artifacts']['arm_a_final_cact_sha256'],'2'*64)
        self.assertEqual(receipt['model_artifacts']['arm_b_early_cact_sha256'],'3'*64)
        self.assertEqual(receipt['model_artifacts']['arm_b_final_cact_sha256'],'4'*64)
        r2=td/'r2.json'; r2.write_text(json.dumps({**receipt,'replica_id':'R2'}))
        final=td/'final.json'
        x=subprocess.run(['python3',str(root/'scripts/stage_c_quality_receipt.py'),'final','--r1',str(r1),'--r2',str(r2),'--output',str(final)],text=True,capture_output=True)
        self.assertEqual(x.returncode,0,x.stderr)
        self.assertEqual(json.loads(final.read_text())['disposition'],'ACCEPTED_STAGE_C_APPLICABILITY_RECOVERY')

class StageCCanonicalStateMetricTest(unittest.TestCase):
    def test_scope_metrics_reports_canonical_state_accuracy_without_changing_route_score(self):
        from scripts.stage_c_quality_receipt import scope_metrics
        rows=make_rows('state',positive_correct=36,negative_no_call=22,dominant=24)
        for i,row in enumerate(rows):
            expected_state={
                'applicability':'NONE' if row['expected']=='NO_CALL' else 'ROUTE',
                'decision':row['expected'],
                'tool_need':'unnecessary' if row['expected']=='NO_CALL' else 'required',
                'evidence_state':'sufficient' if row['expected'] in {'NO_CALL','READY'} else 'insufficient',
                'cost_class':'low','risk_class':'low',
            }
            row['expected_state']=expected_state
            row['predicted_state']=dict(expected_state) if i % 4 != 0 else {**expected_state,'risk_class':'high'}
            row['state_correct']=False
        metrics=scope_metrics(rows)
        self.assertEqual(metrics['canonical_state_n'],96)
        self.assertEqual(metrics['canonical_state_correct'],72)
        self.assertEqual(metrics['canonical_state_accuracy'],0.75)
        self.assertEqual(metrics['negative_no_call'],22)

class StageCFinalProvenanceRegressionTest(unittest.TestCase):
    def test_final_receipt_preserves_each_replica_model_artifacts(self):
        import json, pathlib, subprocess, tempfile
        root=pathlib.Path(__file__).resolve().parents[1]
        td=pathlib.Path(tempfile.mkdtemp(prefix='stage-c-final-provenance-'))
        base={
            'schema':'theseus.needle.stage_c_replica_eval.v1',
            'source':{'experiment_commit':'a'*40},
            'curriculum_manifest_sha256':'7'*64,
            'evaluation':{'accepted':True,'disposition':'ACCEPTED_REPLICA_STAGE_C_APPLICABILITY_RECOVERY'},
            'model_artifacts':{
                'arm_a_final_cact_sha256':'1'*64,
                'arm_b_early_cact_sha256':'2'*64,
                'arm_b_final_cact_sha256':'3'*64,
            },
        }
        r1=td/'r1.json'; r2=td/'r2.json'; out=td/'final.json'
        r1.write_text(json.dumps({**base,'replica_id':'R1'}))
        r2.write_text(json.dumps({**base,'replica_id':'R2','model_artifacts':{
            'arm_a_final_cact_sha256':'4'*64,
            'arm_b_early_cact_sha256':'5'*64,
            'arm_b_final_cact_sha256':'6'*64,
        }}))
        x=subprocess.run(['python3',str(root/'scripts/stage_c_quality_receipt.py'),'final','--r1',str(r1),'--r2',str(r2),'--output',str(out)],text=True,capture_output=True)
        self.assertEqual(x.returncode,0,x.stderr)
        final=json.loads(out.read_text())
        self.assertEqual(final['replicas']['R1']['model_artifacts']['arm_a_final_cact_sha256'],'1'*64)
        self.assertEqual(final['replicas']['R2']['model_artifacts']['arm_b_final_cact_sha256'],'6'*64)


class StageCLatestReviewRegressionTest(unittest.TestCase):
    def test_scope_metrics_recomputes_correctness_from_prediction_and_expected(self):
        rows=make_rows('x',positive_correct=36,negative_no_call=22,dominant=24)
        rows[0]['correct']=not (rows[0]['predicted']==rows[0]['expected'])
        metrics=scope_metrics(rows)
        expected=sum(r['predicted']==r['expected'] for r in rows if r['category'].endswith('_positive'))
        self.assertEqual(metrics['positive_correct'],expected)

    def test_scope_validation_can_bind_expected_model_id(self):
        from scripts.stage_c_quality_receipt import validate_scope_rows
        rows=make_rows('heldout')
        for row in rows:
            row['model_id']='stage-c-B-R1-final'
        expected={r['id']:(r['category'],r['expected']) for r in rows}
        validate_scope_rows(rows,expected,'heldout',expected_model_id='stage-c-B-R1-final')
        rows[0]['model_id']='stage-c-B-R1-early'
        with self.assertRaisesRegex(ValueError,'model_id'):
            validate_scope_rows(rows,expected,'heldout',expected_model_id='stage-c-B-R1-final')

class StageCCanonicalStateIntegrityRegressionTest(unittest.TestCase):
    @staticmethod
    def _state(applicability='ROUTE', decision='READY'):
        return {
            'applicability': applicability,
            'decision': decision,
            'tool_need': 'unnecessary' if applicability == 'NONE' else 'required',
            'evidence_state': 'sufficient' if decision in {'NO_CALL','READY'} else 'insufficient',
            'cost_class': 'low',
            'risk_class': 'low',
        }

    def test_scope_metrics_recomputes_canonical_accuracy_from_states(self):
        rows=make_rows('state',positive_correct=36,negative_no_call=22,dominant=24)
        for row in rows:
            expected=self._state('NONE','NO_CALL') if row['expected']=='NO_CALL' else self._state('ROUTE',row['expected'])
            row['expected_state']=expected
            row['predicted_state']=dict(expected)
            row['state_correct']=False
        metrics=scope_metrics(rows)
        self.assertEqual(metrics['canonical_state_n'],96)
        self.assertEqual(metrics['canonical_state_correct'],96)
        self.assertEqual(metrics['canonical_state_accuracy'],1.0)

    def test_arm_b_scope_requires_complete_consistent_canonical_state(self):
        from scripts.stage_c_quality_receipt import validate_scope_rows
        rows=make_rows('heldout')
        expected={r['id']:(r['category'],r['expected']) for r in rows}
        for row in rows:
            state=self._state('NONE','NO_CALL') if row['expected']=='NO_CALL' else self._state('ROUTE',row['expected'])
            row['expected_state']=state
            row['predicted_state']=dict(state)
            row['state_correct']=True
        validate_scope_rows(rows,expected,'arm_b',require_canonical_state=True)
        rows[0].pop('predicted_state')
        with self.assertRaisesRegex(ValueError,'canonical state'):
            validate_scope_rows(rows,expected,'arm_b',require_canonical_state=True)


class StageCCodexLatestRegressionTest(unittest.TestCase):
    def test_invalid_predicted_state_counts_as_incorrect_instead_of_aborting(self):
        from scripts.stage_c_quality_receipt import validate_scope_rows, scope_metrics
        rows=make_rows('heldout')
        expected={r['id']:(r['category'],r['expected']) for r in rows}
        state=StageCCanonicalStateIntegrityRegressionTest._state
        for row in rows:
            row['expected_state']=state('NONE','NO_CALL') if row['expected']=='NO_CALL' else state('ROUTE',row['expected'])
            row['predicted_state']=dict(row['expected_state'])
            row['state_correct']=True
        rows[0]['predicted_state']='INVALID'
        rows[0]['state_correct']=False
        validate_scope_rows(rows,expected,'arm_b',require_canonical_state=True)
        metrics=scope_metrics(rows)
        self.assertEqual(metrics['canonical_state_n'],96)
        self.assertEqual(metrics['canonical_state_correct'],95)

    def test_only_normal_text_response_counts_as_no_call(self):
        from scripts.run_stage_c_eval import classify_stage_c_response
        self.assertEqual(classify_stage_c_response({'type':'text','text':'no tool needed'},factorized=False)['predicted_route'],'NO_CALL')
        self.assertEqual(classify_stage_c_response({'type':'error','error':'runtime'},factorized=False)['predicted_route'],'INVALID')
        self.assertEqual(classify_stage_c_response({},factorized=False)['predicted_route'],'INVALID')

class StageCCodexEvidenceRegressionTest(unittest.TestCase):
    def test_scope_metrics_reports_canonical_per_field_accuracy_and_confusion(self):
        from scripts.stage_c_quality_receipt import scope_metrics
        rows=make_rows('state',positive_correct=36,negative_no_call=22,dominant=24)
        fields=('applicability','decision','tool_need','evidence_state','cost_class','risk_class')
        for i,row in enumerate(rows):
            expected={
                'applicability':'NONE' if row['expected']=='NO_CALL' else 'ROUTE',
                'decision':row['expected'],
                'tool_need':'unnecessary' if row['expected']=='NO_CALL' else 'required',
                'evidence_state':'sufficient' if row['expected'] in {'NO_CALL','READY'} else 'insufficient',
                'cost_class':'low','risk_class':'low',
            }
            predicted=dict(expected)
            if i % 4 == 0:
                predicted['risk_class']='high'
            row['expected_state']=expected; row['predicted_state']=predicted
        metrics=scope_metrics(rows)
        self.assertEqual(metrics['canonical_field_metrics']['applicability']['accuracy'],1.0)
        self.assertEqual(metrics['canonical_field_metrics']['risk_class']['correct'],72)
        self.assertEqual(metrics['canonical_field_metrics']['risk_class']['n'],96)
        self.assertEqual(metrics['canonical_field_metrics']['risk_class']['confusion']['low->high'],24)
        self.assertEqual(set(metrics['canonical_field_metrics']),set(fields))

    def test_replica_cli_requires_registered_curriculum_manifest_hash(self):
        import pathlib, tempfile, json, subprocess
        root=pathlib.Path(__file__).resolve().parents[1]
        td=pathlib.Path(tempfile.mkdtemp(prefix='stage-c-manifest-hash-'))
        # Reuse the comprehensive CLI fixture by constructing valid scopes and intentionally stale train receipt hashes.
        from tests.test_stage_c_quality import make_rows
        def write(name,rows):
            p=td/name; p.write_text(''.join(json.dumps(r)+'\n' for r in rows)); return p
        a=make_rows('heldout',36,22,24); be=make_rows('heldout',36,22,24); bf=[dict(r) for r in be]
        # Keep registered labels identical across checkpoint slots; alter only predictions.
        bf[0]['predicted']='NO_CALL' if bf[0]['expected']!='NO_CALL' else 'READY'; bf[0]['correct']=bf[0]['predicted']==bf[0]['expected']
        def register(rows,arm,slot,sha):
            for r in rows:
                r['model_id']=f'stage-c-{arm}-R1-{slot}'; r['weights_sha256']=sha
                if arm=='B':
                    st={'applicability':'NONE' if r['expected']=='NO_CALL' else 'ROUTE','decision':r['expected'],'tool_need':'unnecessary' if r['expected']=='NO_CALL' else 'required','evidence_state':'sufficient' if r['expected'] in {'NO_CALL','READY'} else 'insufficient','cost_class':'low','risk_class':'low'}
                    r['expected_state']=st; r['predicted_state']=dict(st); r['state_correct']=True
        register(a,'A','final','2'*64); register(be,'B','early','3'*64); register(bf,'B','final','4'*64)
        at=[{**r,'id':r['id'].replace('heldout-','train-',1),'category':r['category'].replace('heldout_','train_',1)} for r in a]
        bet=[{**r,'id':r['id'].replace('heldout-','train-',1),'category':r['category'].replace('heldout_','train_',1)} for r in be]
        bft=[{**r,'id':r['id'].replace('heldout-','train-',1),'category':r['category'].replace('heldout_','train_',1)} for r in bf]
        semantic=[]
        for r in a: semantic.append({'case_id':r['id'],'split':'heldout','applicability':'none' if r['expected']=='NO_CALL' else 'route','expected_decision':None if r['expected']=='NO_CALL' else r['expected']})
        for r in at: semantic.append({'case_id':r['id'],'split':'train','applicability':'none' if r['expected']=='NO_CALL' else 'route','expected_decision':None if r['expected']=='NO_CALL' else r['expected']})
        sp=td/'semantic.jsonl'; sp.write_text(''.join(json.dumps(r)+'\n' for r in semantic))
        cfg={'seed':101,'epochs':15,'batch_size':16,'lr':1e-4,'lora_rank':16,'lora_alpha':32.0,'max_len':512,'val_split':0.0}
        base='4b0a972d163ffc7678fb3c36bace508114872e9d2ce9e10f225825752d3795bc'
        stale='f'*64
        ta=td/'ta.json'; tb=td/'tb.json'
        ta.write_text(json.dumps({'schema':'theseus.needle.stage_c_train.v1','arm_id':'A','replica_id':'R1','source':{'experiment_commit':'a'*40},'inputs':{'base_checkpoint_sha256':base,'curriculum_manifest_sha256':stale},'training_config':cfg,'artifacts':{'early_cact_sha256':'1'*64,'final_cact_sha256':'2'*64}}))
        tb.write_text(json.dumps({'schema':'theseus.needle.stage_c_train.v1','arm_id':'B','replica_id':'R1','source':{'experiment_commit':'a'*40},'inputs':{'base_checkpoint_sha256':base,'curriculum_manifest_sha256':stale},'training_config':cfg,'artifacts':{'early_cact_sha256':'3'*64,'final_cact_sha256':'4'*64}}))
        args=['python3',str(root/'scripts/stage_c_quality_receipt.py'),'replica','--semantic',str(sp),
          '--arm-a-early',str(write('ae.jsonl',a)),'--arm-a-early-train',str(write('aet.jsonl',at)),
          '--arm-a-final',str(write('af.jsonl',a)),'--arm-a-final-train',str(write('aft.jsonl',at)),
          '--arm-b-early',str(write('be.jsonl',be)),'--arm-b-early-train',str(write('bet.jsonl',bet)),
          '--arm-b-final',str(write('bf.jsonl',bf)),'--arm-b-final-train',str(write('bft.jsonl',bft)),
          '--arm-a-train-receipt',str(ta),'--arm-b-train-receipt',str(tb),'--replica-id','R1','--experiment-commit','a'*40,'--launcher-commit','b'*40,'--run-id','123','--output',str(td/'out.json')]
        x=subprocess.run(args,text=True,capture_output=True)
        self.assertNotEqual(x.returncode,0)
        self.assertIn('curriculum',x.stderr.lower())


    def test_final_rejects_missing_curriculum_manifest_identity(self):
        import json, pathlib, subprocess, tempfile
        root=pathlib.Path(__file__).resolve().parents[1]
        td=pathlib.Path(tempfile.mkdtemp(prefix='stage-c-final-missing-manifest-'))
        base={'schema':'theseus.needle.stage_c_replica_eval.v1','source':{'experiment_commit':'a'*40},'evaluation':{'accepted':True,'disposition':'ACCEPTED_REPLICA_STAGE_C_APPLICABILITY_RECOVERY'},'model_artifacts':{}}
        r1=td/'r1.json'; r2=td/'r2.json'; out=td/'out.json'
        r1.write_text(json.dumps({**base,'replica_id':'R1'})); r2.write_text(json.dumps({**base,'replica_id':'R2'}))
        x=subprocess.run(['python3',str(root/'scripts/stage_c_quality_receipt.py'),'final','--r1',str(r1),'--r2',str(r2),'--output',str(out)],text=True,capture_output=True)
        self.assertNotEqual(x.returncode,0)
        self.assertIn('curriculum',x.stderr.lower())

    def test_replica_pair_preserves_arm_a_early_metrics(self):
        from scripts.stage_c_quality_receipt import evaluate_replica_pair
        a_early=make_rows('aearly',35,20,24)
        a_final=make_rows('afinal',36,21,24)
        b_early=make_rows('bearly',36,22,24)
        b_final=make_rows('bfinal',36,22,24)
        result=evaluate_replica_pair(a_final,b_early,b_final,arm_a_early_heldout=a_early)
        self.assertEqual(result['arm_a_early']['positive_correct'],35)
