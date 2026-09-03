import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
WORKFLOW=ROOT/'.github/workflows/needle-stage-c-dispatch.yml'
TRAIN=ROOT/'scripts/run_stage_c_full_train.sh'
EVAL=ROOT/'scripts/run_stage_c_full_eval.sh'


class StageCFullTrainContractTest(unittest.TestCase):
    def test_train_entrypoint_is_exact_two_phase_and_arm_replica_scoped(self):
        text=TRAIN.read_text(encoding='utf-8')
        self.assertIn('${EXPERIMENT_SHA:?EXPERIMENT_SHA is required}',text)
        self.assertIn('${LAUNCHER_SHA:?LAUNCHER_SHA is required}',text)
        self.assertIn('${ARM_ID:?ARM_ID is required}',text)
        self.assertIn('${REPLICA_ID:?REPLICA_ID is required}',text)
        self.assertIn('A|B',text)
        self.assertIn('R1|R2',text)
        self.assertIn('cactus-needle[train]==2.0.8',text)
        self.assertIn('python3 scripts/build_stage_c_dataset.py --write',text)
        self.assertIn('scripts/audit_stage_c_token_lengths.py',text)
        self.assertIn('scripts/run_stage_c_curriculum_finetune.py',text)
        self.assertIn('--early-out',text)
        self.assertIn('needle build',text)
        self.assertIn('early-${ARM_ID}-${REPLICA_ID}.cact',text)
        self.assertIn('final-${ARM_ID}-${REPLICA_ID}.cact',text)
        self.assertNotIn('run_seeded_finetune.py',text)


class StageCFullEvalContractTest(unittest.TestCase):
    def test_eval_entrypoint_evaluates_early_and_final_without_training(self):
        text=EVAL.read_text(encoding='utf-8')
        self.assertIn('cactus-needle==2.0.8',text)
        self.assertIn('run_realistic_sft_eval.py',text)
        self.assertIn('early-${ARM_ID}-${REPLICA_ID}.cact',text)
        self.assertIn('final-${ARM_ID}-${REPLICA_ID}.cact',text)
        self.assertIn('heldout',text)
        self.assertNotIn('finetune',text)
        self.assertNotIn('needle build',text)


class StageCWorkflowContractTest(unittest.TestCase):
    def test_workflow_is_manual_exact_head_read_only_and_fixed_entrypoints(self):
        text=WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('workflow_dispatch:',text)
        self.assertNotIn('\n  push:',text)
        self.assertNotIn('\n  schedule:',text)
        self.assertIn('experiment_sha:',text)
        self.assertIn('experiment/needle-stage-c-applicability',text)
        self.assertIn('git ls-remote https://github.com/${GITHUB_REPOSITORY}.git refs/heads/experiment/needle-stage-c-applicability',text)
        self.assertIn('contents: read',text)
        self.assertNotIn('secrets.',text)
        self.assertNotIn('${{ inputs.command }}',text)
        self.assertIn('mode:',text)
        self.assertIn('resource_dry_run',text)
        self.assertIn('full',text)

    def test_full_graph_is_two_arms_two_replicas_with_pair_and_final_receipts(self):
        text=WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('arm: [A, B]',text)
        self.assertIn('replica: [R1, R2]',text)
        self.assertIn('ARM_ID: ${{ matrix.arm }}',text)
        self.assertIn('REPLICA_ID: ${{ matrix.replica }}',text)
        self.assertIn('bash scripts/run_stage_c_full_train.sh',text)
        self.assertIn('bash scripts/run_stage_c_full_eval.sh',text)
        self.assertIn('stage_c_quality_receipt.py replica',text)
        self.assertIn('stage_c_quality_receipt.py final',text)
        self.assertIn('needle-stage-c-pair-${{ matrix.replica }}-${{ github.run_id }}',text)
        self.assertIn('needle-stage-c-final-${{ github.run_id }}',text)


if __name__=='__main__':
    unittest.main()
