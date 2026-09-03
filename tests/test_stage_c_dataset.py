import collections
import unittest

from scripts.build_stage_c_dataset import build_stage_c_arms, canonical_decision_state


class StageCDatasetTest(unittest.TestCase):
    def _semantic(self):
        rows=[]
        for i,d in enumerate(["PROBE","READY","UNKNOWN"]):
            rows.append({"case_id":f"train-pos-{i}","split":"train","applicability":"route","expected_decision":d,"query":f"positive {i}"})
        for i in range(3):
            rows.append({"case_id":f"train-neg-{i}","split":"train","applicability":"none","expected_decision":None,"query":f"negative {i}"})
        return rows

    def test_canonical_state_factorizes_applicability_without_rationale(self):
        neg=canonical_decision_state(self._semantic()[-1])
        self.assertEqual(neg, {
            "applicability":"NONE", "decision":"NO_CALL", "tool_need":"unnecessary",
            "evidence_state":"sufficient", "cost_class":"low", "risk_class":"low",
        })
        probe=canonical_decision_state(self._semantic()[0])
        self.assertEqual(probe["applicability"],"ROUTE")
        self.assertEqual(probe["decision"],"PROBE")
        self.assertEqual(probe["tool_need"],"required")
        self.assertEqual(probe["evidence_state"],"insufficient")
        self.assertNotIn("rationale", probe)

    def test_arms_have_equal_budget_and_identical_positive_multiset(self):
        recovery=[
            {"case_id":"train-neg-0","recovery_priority":4.0},
            {"case_id":"train-neg-1","recovery_priority":1.0},
            {"case_id":"train-neg-2","recovery_priority":0.25},
        ]
        arms=build_stage_c_arms(self._semantic(), recovery, negative_budget=3)
        self.assertEqual(len(arms["A"]),6)
        self.assertEqual(len(arms["B"]),6)
        pos_a=collections.Counter(r["case_id"] for r in arms["A"] if r["canonical_state"]["applicability"]=="ROUTE")
        pos_b=collections.Counter(r["case_id"] for r in arms["B"] if r["canonical_state"]["applicability"]=="ROUTE")
        self.assertEqual(pos_a,pos_b)

    def test_arm_a_replays_negatives_uniformly_and_arm_b_prioritizes_failures(self):
        recovery=[
            {"case_id":"train-neg-0","recovery_priority":4.0},
            {"case_id":"train-neg-1","recovery_priority":1.0},
            {"case_id":"train-neg-2","recovery_priority":0.25},
        ]
        arms=build_stage_c_arms(self._semantic(), recovery, negative_budget=3)
        a=collections.Counter(r["case_id"] for r in arms["A"] if r["canonical_state"]["applicability"]=="NONE")
        b=collections.Counter(r["case_id"] for r in arms["B"] if r["canonical_state"]["applicability"]=="NONE")
        self.assertEqual(a, collections.Counter({"train-neg-0":1,"train-neg-1":1,"train-neg-2":1}))
        self.assertGreater(b["train-neg-0"], b["train-neg-2"])
        self.assertEqual(sum(b.values()),3)

    def test_heldout_rows_are_forbidden(self):
        rows=self._semantic()+[{"case_id":"heldout-neg","split":"heldout","applicability":"none","expected_decision":None,"query":"heldout"}]
        with self.assertRaisesRegex(ValueError,"heldout"):
            build_stage_c_arms(rows, [], negative_budget=3)

    def test_output_is_deterministic(self):
        recovery=[{"case_id":f"train-neg-{i}","recovery_priority":p} for i,p in enumerate([4.0,1.0,0.25])]
        self.assertEqual(build_stage_c_arms(self._semantic(), recovery, 3), build_stage_c_arms(self._semantic(), recovery, 3))


if __name__ == '__main__':
    unittest.main()

class StageCArtifactTest(unittest.TestCase):
    def test_outputs_are_byte_stable_equal_budget_and_manifest_bound(self):
        import hashlib, json
        from scripts.build_stage_c_dataset import build_outputs
        semantic=StageCDatasetTest()._semantic()
        recovery=[{"case_id":f"train-neg-{i}","recovery_priority":p} for i,p in enumerate([4.0,1.0,0.25])]
        schema={"name":"route","parameters":{"type":"object","properties":{"decision":{"type":"string","enum":["PROBE","READY","UNKNOWN"]}},"required":["decision"]}}
        prefix="Use route to classify the following evidence:\n\n"
        first=build_outputs(semantic,recovery,3,schema,prefix)
        second=build_outputs(semantic,recovery,3,schema,prefix)
        self.assertEqual(first,second)
        for arm in ("A","B"):
            train=first["files"][f"data/arm-{arm.lower()}.train.needle.jsonl"]
            self.assertEqual(len(train.decode().splitlines()),6)
            canonical=first["files"][f"state/arm-{arm.lower()}.canonical.jsonl"]
            self.assertEqual(len(canonical.decode().splitlines()),6)
        manifest=json.loads(first["files"]["manifests/stage-c-dataset-manifest.json"])
        self.assertEqual(manifest["negative_budget_per_arm"],3)
        self.assertEqual(manifest["arm_rows"],{"A":6,"B":6})
        for binding in manifest["bindings"]:
            payload=first["files"][binding["path"]]
            self.assertEqual(hashlib.sha256(payload).hexdigest(),binding["sha256"])
