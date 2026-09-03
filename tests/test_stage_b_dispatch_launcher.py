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
        self.assertIn('git ls-remote origin refs/heads/experiment/needle-realistic-sft-spec', text)
        self.assertIn('test "$REMOTE_SHA" = "$REQUESTED_SHA"', text)
        self.assertIn('ref: ${{ inputs.experiment_sha }}', text)
        self.assertIn('bash scripts/run_realistic_sft_resource_dry_run.sh', text)
        self.assertIn('contents: read', text)
        self.assertNotIn('needle finetune', text)
        self.assertNotIn('run_seeded_finetune.py', text)
        self.assertNotIn('${{ inputs.command }}', text)

if __name__ == '__main__':
    unittest.main()
