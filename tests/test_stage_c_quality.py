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
        at=write('at.jsonl',at_rows); bet=write('bet.jsonl',bet_rows); bft=write('bft.jsonl',bft_rows)
        semantic=td/'semantic.jsonl'
        semantic_rows=[]
        for row in a_rows:
            semantic_rows.append({'case_id':row['id'],'split':'heldout','applicability':'none' if row['expected']=='NO_CALL' else 'route','expected_decision':None if row['expected']=='NO_CALL' else row['expected']})
        for row in at_rows:
            semantic_rows.append({'case_id':row['id'],'split':'train','applicability':'none' if row['expected']=='NO_CALL' else 'route','expected_decision':None if row['expected']=='NO_CALL' else row['expected']})
        semantic.write_text(''.join(json.dumps(r)+'\n' for r in semantic_rows))
        train_a=td/'train-a.json'; train_b=td/'train-b.json'
        train_a.write_text(json.dumps({'schema':'theseus.needle.stage_c_train.v1','arm_id':'A','replica_id':'R1','source':{'experiment_commit':'a'*40},'artifacts':{'early_cact_sha256':'1'*64,'final_cact_sha256':'2'*64}}))
        train_b.write_text(json.dumps({'schema':'theseus.needle.stage_c_train.v1','arm_id':'B','replica_id':'R1','source':{'experiment_commit':'a'*40},'artifacts':{'early_cact_sha256':'3'*64,'final_cact_sha256':'4'*64}}))
        r1=td/'r1.json'
        cmd=['python3',str(root/'scripts/stage_c_quality_receipt.py'),'replica','--semantic',str(semantic),'--arm-a-final',str(a),'--arm-a-final-train',str(at),'--arm-b-early',str(be),'--arm-b-early-train',str(bet),'--arm-b-final',str(bf),'--arm-b-final-train',str(bft),'--arm-a-train-receipt',str(train_a),'--arm-b-train-receipt',str(train_b),'--replica-id','R1','--experiment-commit','a'*40,'--launcher-commit','b'*40,'--run-id','123','--output',str(r1)]
        x=subprocess.run(cmd,text=True,capture_output=True)
        self.assertEqual(x.returncode,0,x.stderr)
        receipt=json.loads(r1.read_text())
        self.assertEqual(receipt['schema'],'theseus.needle.stage_c_replica_eval.v1')
        self.assertTrue(receipt['evaluation']['accepted'])
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
            row['state_correct']=(i % 4 != 0)
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
