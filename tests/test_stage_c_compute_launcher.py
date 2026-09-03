import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
WORKFLOW=ROOT/'.github/workflows/needle-stage-c-compute-sidecar.yml'

class StageCComputeLauncherContractTest(unittest.TestCase):
    def test_launcher_is_manual_read_only_and_executes_experiment_sidecar(self):
        text=WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('workflow_dispatch:',text)
        self.assertIn('experiment_sha:',text)
        self.assertIn('contents: read',text)
        self.assertIn('ref: ${{ inputs.experiment_sha }}',text)
        self.assertIn('mcp-sympy==0.1.0',text)
        self.assertIn('npm ci --ignore-scripts --prefix verification/stage-c-sidecars',text)
        self.assertIn('node scripts/stage_c_compute_verifier.mjs',text)
        self.assertNotIn('needle finetune',text)
        self.assertNotIn('run_stage_c_full_train',text)

if __name__=='__main__':
    unittest.main()
