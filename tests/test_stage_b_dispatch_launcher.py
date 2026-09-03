import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github' / 'workflows' / 'needle-stage-b-dispatch.yml'

class StageBDispatchLauncherContractTest(unittest.TestCase):
    def test_launcher_is_manual_exact_head_and_fixed_entrypoint_only(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('workflow_dispatch:', text)
        self.assertNotIn('\n  push:', text)
        self.assertNotIn('\n  schedule:', text)
        self.assertIn('experiment_sha:', text)
        self.assertIn('^[0-9a-f]{40}$', text)
        self.assertIn('BLOCKED_INVALID_SHA', text)
        self.assertIn('experiment/needle-realistic-sft-spec', text)
        self.assertNotIn('git ls-remote origin ', text)
        self.assertIn('git ls-remote https://github.com/${GITHUB_REPOSITORY}.git refs/heads/experiment/needle-realistic-sft-spec', text)
        self.assertIn('test "$REMOTE_SHA" = "$REQUESTED_SHA"', text)
        self.assertIn('ref: ${{ inputs.experiment_sha }}', text)
        self.assertIn('bash scripts/run_realistic_sft_resource_dry_run.sh', text)
        self.assertIn('EXPERIMENT_SHA: ${{ inputs.experiment_sha }}', text)
        self.assertIn('LAUNCHER_SHA: ${{ github.sha }}', text)
        self.assertIn('actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02', text)
        self.assertIn('if: always()', text)
        self.assertIn('needle-stage-b-resource-${{ github.run_id }}', text)
        for evidence_dir in ['artifacts/', 'results/', 'logs/', 'metrics/']:
            self.assertIn(evidence_dir, text)
        self.assertIn('contents: read', text)
        self.assertNotIn('needle finetune', text)
        self.assertNotIn('run_seeded_finetune.py', text)
        self.assertNotIn('${{ inputs.command }}', text)

    def test_full_mode_is_two_independent_replicas_with_paired_eval_and_final_aggregate(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('mode:', text)
        self.assertIn('resource_dry_run', text)
        self.assertIn('full', text)
        self.assertIn("if: inputs.mode == 'full'", text)
        self.assertIn('matrix:', text)
        self.assertIn('replica: [R1, R2]', text)
        self.assertIn('timeout-minutes: 210', text)
        self.assertIn('REPLICA_ID: ${{ matrix.replica }}', text)
        self.assertIn('bash scripts/run_realistic_sft_full_train.sh', text)
        self.assertIn('bash scripts/run_realistic_sft_full_eval.sh', text)
        self.assertIn('actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093', text)
        self.assertIn('needle-stage-b-train-${{ matrix.replica }}-${{ github.run_id }}', text)
        self.assertIn('needle-stage-b-eval-${{ matrix.replica }}-${{ github.run_id }}', text)
        self.assertIn('realistic_sft_quality_receipt.py final', text)
        self.assertIn('eval-receipt-R1.json', text)
        self.assertIn('eval-receipt-R2.json', text)
        self.assertIn('needle-stage-b-final-${{ github.run_id }}', text)
        self.assertIn('python-version: "3.12"', text)
        self.assertNotIn('${{ inputs.command }}', text)


if __name__ == '__main__':
    unittest.main()
