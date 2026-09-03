import json
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
        arms=build_stage_c_arms(self._semantic(), recovery, additional_negative_budget=3)
        self.assertEqual(len(arms["A"]),9)
        self.assertEqual(len(arms["B"]),9)
        pos_a=collections.Counter(r["case_id"] for r in arms["A"] if r["canonical_state"]["applicability"]=="ROUTE")
        pos_b=collections.Counter(r["case_id"] for r in arms["B"] if r["canonical_state"]["applicability"]=="ROUTE")
        self.assertEqual(pos_a,pos_b)

    def test_arm_a_replays_negatives_uniformly_and_arm_b_prioritizes_failures(self):
        recovery=[
            {"case_id":"train-neg-0","recovery_priority":4.0},
            {"case_id":"train-neg-1","recovery_priority":1.0},
            {"case_id":"train-neg-2","recovery_priority":0.25},
        ]
        arms=build_stage_c_arms(self._semantic(), recovery, additional_negative_budget=3)
        a=collections.Counter(r["case_id"] for r in arms["A"] if r["canonical_state"]["applicability"]=="NONE")
        b=collections.Counter(r["case_id"] for r in arms["B"] if r["canonical_state"]["applicability"]=="NONE")
        self.assertEqual(a, collections.Counter({"train-neg-0":2,"train-neg-1":2,"train-neg-2":2}))
        self.assertGreater(b["train-neg-0"], b["train-neg-2"])
        self.assertGreaterEqual(b["train-neg-2"],1)
        self.assertEqual(sum(b.values()),6)

    def test_heldout_rows_are_forbidden(self):
        rows=self._semantic()+[{"case_id":"heldout-neg","split":"heldout","applicability":"none","expected_decision":None,"query":"heldout"}]
        with self.assertRaisesRegex(ValueError,"heldout"):
            build_stage_c_arms(rows, [], additional_negative_budget=3)

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
            self.assertEqual(len(train.decode().splitlines()),9)
            canonical=first["files"][f"state/arm-{arm.lower()}.canonical.jsonl"]
            self.assertEqual(len(canonical.decode().splitlines()),9)
        manifest=json.loads(first["files"]["manifests/stage-c-dataset-manifest.json"])
        self.assertEqual(manifest["additional_negative_budget_per_arm"],3)
        self.assertEqual(manifest["arm_rows"],{"A":9,"B":9})
        for binding in manifest["bindings"]:
            payload=first["files"][binding["path"]]
            self.assertEqual(hashlib.sha256(payload).hexdigest(),binding["sha256"])

class StageCRecoverySeedProvenanceTest(unittest.TestCase):
    def test_committed_seed_is_two_replica_consensus_and_train_only(self):
        import json, pathlib
        root=pathlib.Path(__file__).resolve().parents[1]
        seed_path=root/'experiments/needle-stage-c-applicability/source/stage-b-recovery-seed.json'
        seed=json.loads(seed_path.read_text(encoding='utf-8'))
        self.assertEqual(seed['schema_version'],'needle-stage-c-recovery-seed-v1')
        self.assertEqual(seed['stage_b_workflow_run_id'],33722433205)
        self.assertEqual(len(seed['replicas']),2)
        self.assertEqual({r['replica_id'] for r in seed['replicas']},{'R1','R2'})
        self.assertEqual(len(seed['false_call_case_ids']),55)
        self.assertEqual(len(set(seed['false_call_case_ids'])),55)
        self.assertTrue(all(x.startswith('train-negative-') for x in seed['false_call_case_ids']))
        self.assertTrue(all(len(r['tuned_train_sha256'])==64 for r in seed['replicas']))
        semantic=[json.loads(x) for x in (root/'experiments/needle-realistic-sft/source/semantic-cases.jsonl').read_text().splitlines() if x.strip()]
        train_negative={r['case_id'] for r in semantic if r['split']=='train' and r['applicability']=='none'}
        heldout={r['case_id'] for r in semantic if r['split']=='heldout'}
        self.assertTrue(set(seed['false_call_case_ids']) <= train_negative)
        self.assertTrue(set(seed['false_call_case_ids']).isdisjoint(heldout))

class StageCRealCurriculumProjectionTest(unittest.TestCase):
    def test_real_stage_b_source_materializes_exact_stage_c_phase_geometry_without_heldout_leakage(self):
        import json, pathlib, collections
        from scripts.build_stage_c_dataset import build_curriculum_outputs
        root=pathlib.Path(__file__).resolve().parents[1]
        semantic=[json.loads(x) for x in (root/'experiments/needle-realistic-sft/source/semantic-cases.jsonl').read_text().splitlines() if x.strip()]
        seed=json.loads((root/'experiments/needle-stage-c-applicability/source/stage-b-recovery-seed.json').read_text())
        policy=json.loads((root/'experiments/needle-stage-c-applicability/contract/curriculum-policy.json').read_text())
        schema=json.loads((root/'experiments/needle-realistic-sft/contract/route-schema.json').read_text())
        prefix=(root/'experiments/needle-realistic-sft/contract/route-positive-prefix.txt').read_text()
        out=build_curriculum_outputs(semantic,seed,policy,schema,prefix)
        self.assertEqual({k:len(v) for k,v in out['arms']['early'].items()},{'A':417,'B':417})
        self.assertEqual({k:len(v) for k,v in out['arms']['reduced'].items()},{'A':390,'B':390})
        heldout={r['case_id'] for r in semantic if r['split']=='heldout'}
        all_train_neg={r['case_id'] for r in semantic if r['split']=='train' and r['applicability']=='none'}
        failures=set(seed['false_call_case_ids'])
        successes=all_train_neg-failures
        self.assertEqual(len(failures),55)
        self.assertEqual(len(successes),5)
        for phase in ('early','reduced'):
            for arm in ('A','B'):
                ids=[r['case_id'] for r in out['arms'][phase][arm]]
                self.assertTrue(set(ids).isdisjoint(heldout))
                neg_counts=collections.Counter(x for x in ids if x in all_train_neg)
                self.assertEqual(set(neg_counts),all_train_neg)
                self.assertTrue(all(neg_counts[x]>=1 for x in all_train_neg))
            b_counts=collections.Counter(r['case_id'] for r in out['arms'][phase]['B'] if r['case_id'] in all_train_neg)
            self.assertGreater(sum(b_counts[x] for x in failures)/len(failures), sum(b_counts[x] for x in successes)/len(successes))
        manifest=json.loads(out['files']['manifests/stage-c-curriculum-manifest.json'])
        self.assertEqual(manifest['phase_rows'],{'early':{'A':417,'B':417},'reduced':{'A':390,'B':390}})

class StageCCurriculumCliTest(unittest.TestCase):
    def test_cli_materializes_registered_curriculum(self):
        import pathlib, shutil, subprocess, tempfile, json
        root=pathlib.Path(__file__).resolve().parents[1]
        td=pathlib.Path(tempfile.mkdtemp(prefix='needle-stage-c-cli-'))
        for rel in [
            'experiments/needle-realistic-sft/source/semantic-cases.jsonl',
            'experiments/needle-realistic-sft/contract/route-schema.json',
            'experiments/needle-realistic-sft/contract/route-positive-prefix.txt',
            'experiments/needle-stage-c-applicability/source/stage-b-recovery-seed.json',
            'experiments/needle-stage-c-applicability/contract/curriculum-policy.json',
        ]:
            src=root/rel; dst=td/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
        result=subprocess.run(['python3',str(root/'scripts/build_stage_c_dataset.py'),'--write','--root',str(td)],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        base=td/'experiments/needle-stage-c-applicability'
        self.assertEqual(len((base/'data/early.arm-a.train.needle.jsonl').read_text().splitlines()),417)
        self.assertEqual(len((base/'data/early.arm-b.train.needle.jsonl').read_text().splitlines()),417)
        self.assertEqual(len((base/'data/reduced.arm-a.train.needle.jsonl').read_text().splitlines()),390)
        self.assertEqual(len((base/'data/reduced.arm-b.train.needle.jsonl').read_text().splitlines()),390)
        manifest=json.loads((base/'manifests/stage-c-curriculum-manifest.json').read_text())
        self.assertEqual(manifest['phase_rows']['early'],{'A':417,'B':417})

class StageCCodexP1RegressionTest(unittest.TestCase):
    def test_arm_b_supervision_contains_structured_policy_state_and_separate_route_action(self):
        from scripts.build_stage_c_dataset import build_outputs, POLICY_STATE_SCHEMA
        semantic=self._semantic_fixture()
        recovery=[{'case_id':'n1','recovery_priority':1.0}]
        prefix="Use route to classify the following evidence:\n\n"
        route_schema={'name':'route','parameters':{'type':'object','properties':{'decision':{'type':'string','enum':['PROBE','READY','UNKNOWN']}},'required':['decision']}}
        out=build_outputs(semantic,recovery,1,route_schema,prefix)
        b_rows=[json.loads(x) for x in out['files']['data/arm-b.train.needle.jsonl'].decode().splitlines()]
        positive=next(r for r in b_rows if r['query'].startswith(prefix))
        negative=next(r for r in b_rows if not r['query'].startswith(prefix))
        self.assertEqual(positive['tools'],[POLICY_STATE_SCHEMA,route_schema])
        self.assertEqual(positive['answers'][0]['name'],'policy_state')
        self.assertEqual(positive['answers'][0]['arguments']['applicability'],'ROUTE')
        self.assertEqual(positive['answers'][1]['name'],'route')
        self.assertEqual(negative['tools'],[POLICY_STATE_SCHEMA,route_schema])
        self.assertEqual([a['name'] for a in negative['answers']],['policy_state'])
        self.assertEqual(negative['answers'][0]['arguments']['applicability'],'NONE')

    def test_recovery_scale_is_relative_to_nonzero_ordinary_negative_baseline(self):
        from scripts.build_stage_c_dataset import build_stage_c_arms
        semantic=self._semantic_fixture()
        # n1 is recovery; n2 is ordinary. A stays uniform. B must change as scale changes.
        early=build_stage_c_arms(semantic,[{'case_id':'n1','recovery_priority':1.0}],additional_negative_budget=12)
        reduced=build_stage_c_arms(semantic,[{'case_id':'n1','recovery_priority':0.5}],additional_negative_budget=12)
        def counts(rows):
            out={}
            for r in rows:
                if r['canonical_state']['applicability']=='NONE': out[r['case_id']]=out.get(r['case_id'],0)+1
            return out
        self.assertEqual(counts(early['A']),counts(reduced['A']))
        self.assertNotEqual(counts(early['B']),counts(reduced['B']))
        self.assertGreater(counts(early['B'])['n1'],counts(early['B'])['n2'])
        self.assertGreaterEqual(counts(reduced['B'])['n1'],counts(reduced['B'])['n2'])

    @staticmethod
    def _semantic_fixture():
        return [
            {'case_id':'p1','split':'train','applicability':'route','expected_decision':'PROBE','query':'positive'},
            {'case_id':'n1','split':'train','applicability':'none','expected_decision':None,'query':'negative one'},
            {'case_id':'n2','split':'train','applicability':'none','expected_decision':None,'query':'negative two'},
        ]
