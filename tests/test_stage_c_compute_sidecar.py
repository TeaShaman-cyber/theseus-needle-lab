import json
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]

class StageCComputeSidecarContractTest(unittest.TestCase):
    def test_claim_freezes_exact_allocation_arithmetic(self):
        claim=json.loads((ROOT/'experiments/needle-stage-c-applicability/verification/stage-c-compute-claim.json').read_text())
        self.assertEqual(claim['schema_version'],'theseus.needle.stage_c_compute_claim.v1')
        self.assertEqual(claim['authority'],'DIAGNOSTIC_ONLY')
        self.assertEqual(claim['inputs']['recovery_cases'],55)
        self.assertEqual(claim['inputs']['ordinary_negative_cases'],5)
        self.assertEqual(claim['inputs']['early_recovery_weight'],'2')
        self.assertEqual(claim['inputs']['early_ordinary_weight'],'1')
        self.assertEqual(claim['inputs']['reduced_recovery_weight'],'3/2')
        self.assertEqual(claim['inputs']['reduced_ordinary_weight'],'1')

    def test_verifier_has_explicit_wolfram_to_sympy_fallback_and_inconclusive_status(self):
        text=(ROOT/'scripts/stage_c_compute_verifier.mjs').read_text()
        self.assertIn('https://agenttools.wolfram.com/mcp.WolframLanguageEvaluator',text)
        self.assertIn('sympy.sympy_simplify',text)
        self.assertIn("backend = 'wolfram'",text)
        self.assertIn("backend = 'sympy'",text)
        self.assertIn('INCONCLUSIVE_SIDECAR',text)
        self.assertIn('mcporter@0.9.0',text)
        self.assertIn('raw_transport_sha256',text)
        self.assertIn("authority: 'DIAGNOSTIC_ONLY'",text)

    def test_sidecar_workflow_is_read_only_and_pins_local_sympy(self):
        text=(ROOT/'.github/workflows/needle-stage-c-compute-sidecar.yml').read_text()
        self.assertIn('contents: read',text)
        self.assertIn('mcp-sympy==0.1.0',text)
        self.assertIn('npm ci --ignore-scripts --prefix verification/stage-c-sidecars',text)
        self.assertIn('stage_c_compute_verifier.mjs',text)
        self.assertNotIn('needle finetune',text)
        self.assertNotIn('run_stage_c_full_train',text)

if __name__=='__main__':
    unittest.main()
