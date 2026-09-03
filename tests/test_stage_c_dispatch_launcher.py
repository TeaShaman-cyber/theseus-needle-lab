import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github' / 'workflows' / 'needle-stage-c-dispatch.yml'


class StageCDispatchLauncherContractTest(unittest.TestCase):
    def test_launcher_is_manual_exact_head_and_fixed_entrypoints_only(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('workflow_dispatch:', text)
        self.assertNotIn('\n  push:', text)
        self.assertNotIn('\n  schedule:', text)
        self.assertIn('experiment_sha:', text)
        self.assertIn('experiment/needle-stage-c-applicability', text)
        self.assertIn('test "$REMOTE_SHA" = "$REQUESTED_SHA"', text)
        self.assertIn('ref: ${{ inputs.experiment_sha }}', text)
        self.assertIn('resource_dry_run', text)
        self.assertIn('full', text)
        self.assertIn('bash scripts/run_stage_c_full_train.sh', text)
        self.assertIn('bash scripts/run_stage_c_full_eval.sh', text)
        self.assertIn('contents: read', text)
        self.assertNotIn('${{ inputs.command }}', text)
        self.assertNotIn('secrets.', text)


if __name__ == '__main__':
    unittest.main()
