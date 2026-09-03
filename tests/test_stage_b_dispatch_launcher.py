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

if __name__ == '__main__':
    unittest.main()
