import json
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
POLICY=ROOT/'experiments/needle-stage-c-applicability/contract/curriculum-policy.json'
RUNNER=ROOT/'scripts/run_stage_c_curriculum_finetune.py'


class StageCCurriculumPolicyTest(unittest.TestCase):
    def test_policy_freezes_two_continuous_phases_and_equal_arm_budget(self):
        p=json.loads(POLICY.read_text(encoding='utf-8'))
        self.assertEqual(p['schema_version'],'needle-stage-c-curriculum-policy-v1')
        self.assertEqual(p['total_epochs'],15)
        self.assertEqual(p['base_positive_rows'],300)
        self.assertEqual(p['base_negative_rows'],60)
        self.assertEqual(p['phases'],[
            {'name':'early','epochs':10,'additional_negative_presentations':57,'recovery_weight_scale':1.0},
            {'name':'reduced','epochs':5,'additional_negative_presentations':30,'recovery_weight_scale':0.5},
        ])
        self.assertEqual(10*(300+60+60)+5*(300+60+30),6150)


class StageCCurriculumRunnerContractTest(unittest.TestCase):
    def test_runner_initializes_lora_and_optimizer_once_across_both_phases(self):
        text=RUNNER.read_text(encoding='utf-8')
        self.assertNotIn('finetune_local(',text)
        self.assertEqual(text.count('init_lora(params,'),1)
        self.assertEqual(text.count('optimizer.init(lora)'),1)
        self.assertIn('for phase in phases:',text)
        self.assertIn('phase["epochs"]',text)
        self.assertIn('load_jsonl(phase["path"]',text)
        self.assertIn('pickle.dump(',text)
        self.assertIn('cactus-needle==2.0.8',text)

    def test_runner_requires_exact_early_and_reduced_paths(self):
        text=RUNNER.read_text(encoding='utf-8')
        self.assertIn('--early-jsonl',text)
        self.assertIn('--reduced-jsonl',text)
        self.assertIn('--policy',text)
        self.assertIn('--seed',text)
        self.assertIn('--checkpoint',text)
        self.assertIn('--early-out',text)
        self.assertIn('--out',text)
        self.assertIn('if phase["name"] == "early":',text)
        self.assertIn('_write_adapter(args.early_out',text)


if __name__=='__main__':
    unittest.main()

class StageCMeasuredMaxLenContractTest(unittest.TestCase):
    def test_factorized_stage_c_uses_512_everywhere(self):
        p=json.loads(POLICY.read_text(encoding='utf-8'))
        self.assertEqual(p['max_len'],512)
        runner=RUNNER.read_text(encoding='utf-8')
        train=(ROOT/'scripts/run_stage_c_full_train.sh').read_text(encoding='utf-8')
        workflow=(ROOT/'.github/workflows/needle-stage-c-dispatch.yml').read_text(encoding='utf-8')
        self.assertIn('default=512',runner)
        self.assertIn('--max-len 512',train)
        self.assertIn('--max-len 512',workflow)
