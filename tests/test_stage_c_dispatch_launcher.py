import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github' / 'workflows' / 'needle-stage-c-dispatch.yml'

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
        self.assertIn('eval-artifacts/A/A-final-heldout-${{ matrix.replica }}.jsonl',text)
        self.assertIn('eval-artifacts/B/B-early-heldout-${{ matrix.replica }}.jsonl',text)
        self.assertNotIn('eval-artifacts/A/results/',text)
        self.assertIn('stage_c_quality_receipt.py final',text)
        self.assertIn('needle-stage-c-pair-${{ matrix.replica }}-${{ github.run_id }}',text)
        self.assertIn('needle-stage-c-final-${{ github.run_id }}',text)


if __name__=='__main__':
    unittest.main()

