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
        arm_a=make_rows("a",positive_correct=34,negative_no_call=16,dominant=24)
        arm_b=make_rows("b",positive_correct=36,negative_no_call=22,dominant=24)
        reduced=make_rows("br",positive_correct=35,negative_no_call=21,dominant=24)
        return arm_a,arm_b,reduced

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

    def test_recovery_floor_failure_has_registered_disposition(self):
        a,b,r=self.good_pair()
        result=evaluate_replica_pair(a,make_rows("b",36,19,24),r)
        self.assertEqual(result["disposition"],"REJECTED_APPLICABILITY_RECOVERY_FAILED")

    def test_positive_floor_failure_has_registered_disposition(self):
        a,b,r=self.good_pair()
        result=evaluate_replica_pair(a,make_rows("b",31,22,24),r)
        self.assertEqual(result["disposition"],"REJECTED_POSITIVE_RETENTION_REGRESSION")

    def test_semantic_collapse_is_rejected(self):
        a,b,r=self.good_pair()
        collapsed=make_rows("b",36,22,60)
        result=evaluate_replica_pair(a,collapsed,r)
        self.assertEqual(result["disposition"],"REJECTED_DECISION_COLLAPSE")

    def test_arm_b_must_beat_control_without_worse_positive_correctness(self):
        a=make_rows("a",36,22,24)
        b=make_rows("b",35,22,24)
        r=make_rows("r",35,21,24)
        result=evaluate_replica_pair(a,b,r)
        self.assertEqual(result["disposition"],"INCONCLUSIVE_RECOVERY_SPECIFICITY")

    def test_recovery_must_survive_reduced_weight_phase(self):
        a,b,_=self.good_pair()
        r=make_rows("r",35,18,24)
        result=evaluate_replica_pair(a,b,r)
        self.assertFalse(result["reduced_weight_retention_ok"])
        self.assertEqual(result["disposition"],"REJECTED_APPLICABILITY_RECOVERY_FAILED")

    def test_final_acceptance_requires_both_replicas(self):
        a,b,r=self.good_pair()
        good=evaluate_replica_pair(a,b,r)
        bad=evaluate_replica_pair(a,make_rows("b2",36,19,24),r)
        self.assertEqual(final_disposition(good,good),"ACCEPTED_STAGE_C_APPLICABILITY_RECOVERY")
        self.assertEqual(final_disposition(good,bad),"REJECTED_APPLICABILITY_RECOVERY_FAILED")


if __name__ == '__main__':
    unittest.main()
