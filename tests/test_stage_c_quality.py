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
        a=write('a.jsonl',make_rows('a',34,16,24))
        be=write('be.jsonl',make_rows('be',36,22,24))
        bf=write('bf.jsonl',make_rows('bf',35,21,24))
        train_a=td/'train-a.json'; train_b=td/'train-b.json'
        train_a.write_text(json.dumps({'schema':'theseus.needle.stage_c_train.v1','arm_id':'A','replica_id':'R1','source':{'experiment_commit':'a'*40},'artifacts':{'early_cact_sha256':'1'*64,'final_cact_sha256':'2'*64}}))
        train_b.write_text(json.dumps({'schema':'theseus.needle.stage_c_train.v1','arm_id':'B','replica_id':'R1','source':{'experiment_commit':'a'*40},'artifacts':{'early_cact_sha256':'3'*64,'final_cact_sha256':'4'*64}}))
        r1=td/'r1.json'
        cmd=['python3',str(root/'scripts/stage_c_quality_receipt.py'),'replica','--arm-a-final',str(a),'--arm-b-early',str(be),'--arm-b-final',str(bf),'--arm-a-train-receipt',str(train_a),'--arm-b-train-receipt',str(train_b),'--replica-id','R1','--experiment-commit','a'*40,'--launcher-commit','b'*40,'--run-id','123','--output',str(r1)]
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
