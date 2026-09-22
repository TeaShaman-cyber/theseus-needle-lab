import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "execution-recovery-canary.yml"


class ExecutionRecoveryCanaryContractTests(unittest.TestCase):
    def test_canary_preserves_failed_command_evidence_then_reads_it_back(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("github.event.pull_request.head.sha", text)
        self.assertIn("continue-on-error: true", text)
        self.assertIn("exit 17", text)
        self.assertIn("steps.exercise.outcome", text)
        self.assertIn("actions/upload-artifact@", text)
        self.assertIn("actions/download-artifact@", text)
        self.assertIn("--expected-execution-status FAILED", text)
        self.assertIn("--expected-lifecycle-state ARTIFACT_PROVENANCE", text)
        self.assertIn("RECOVERY_READBACK_PASS", text)
        self.assertIn("retention-days: 7", text)


if __name__ == "__main__":
    unittest.main()
