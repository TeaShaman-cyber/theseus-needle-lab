import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WF=ROOT/'.github'/'workflows'/'typed-decision-benchmark-v1.yml'

class TypedDecisionWorkflowTests(unittest.TestCase):
    def test_workflow_is_manual_exact_sha_only(self):
        text=WF.read_text(encoding='utf-8')
        self.assertIn('workflow_dispatch:',text)
        self.assertNotIn('pull_request:',text)
        self.assertNotIn('schedule:',text)
        self.assertIn('test "$LAUNCHER_SHA" = "$EXPERIMENT_SHA"',text)
        self.assertIn('refs/heads/main',text)

    def test_matrix_is_four_arms_and_fail_fast_false(self):
        text=WF.read_text(encoding='utf-8')
        self.assertIn('fail-fast: false',text)
        for candidate in ('baseline_constant_unknown','needle3_base','semif_qwen3_0_6b_q8','kev_0_8b'): self.assertIn('candidate: '+candidate,text)

    def test_workflow_uses_existing_telemetry_and_readback(self):
        text=WF.read_text(encoding='utf-8')
        self.assertIn('scripts/execution_telemetry.py run',text)
        self.assertIn('--stage typed_decision_benchmark_v1',text)
        self.assertIn('scripts/readback_typed_decision_benchmark.py',text)
        self.assertIn('if: ${{ always()',text)

    def test_workflow_does_not_run_from_repository_qa(self):
        qa=(ROOT/'.github'/'workflows'/'docs-check.yml').read_text(encoding='utf-8')
        self.assertNotIn('typed_decision_benchmark',qa)

if __name__=='__main__': unittest.main()
