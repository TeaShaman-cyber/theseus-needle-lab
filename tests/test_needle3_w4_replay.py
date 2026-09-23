import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "needle3_w4_replay", SCRIPTS / "needle3_w4_replay.py"
)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class Needle3W4ReplayTests(unittest.TestCase):
    def test_branch_workflow_binds_launcher_identity_for_stage_wrapper(self):
        text = (ROOT / ".github" / "workflows" / "needle3-deployment-canary.yml").read_text()
        start = text.index("  w4_replay:")
        end = text.index("  w4_readback:")
        section = text[start:end]
        self.assertIn("LAUNCHER_SHA: ${{ github.workflow_sha }}", section)

    def test_diagnostic_exact_match(self):
        self.assertEqual(
            module.diagnostic_label(
                {"prediction_mismatch_count": 4},
                {"prediction_mismatch_count": 0},
            ),
            "W4_PREDICTIONS_MATCH_BUILT",
        )

    def test_diagnostic_reduces_divergence(self):
        self.assertEqual(
            module.diagnostic_label(
                {"prediction_mismatch_count": 4},
                {"prediction_mismatch_count": 2},
            ),
            "W4_REDUCES_DIVERGENCE",
        )

    def test_diagnostic_does_not_explain_divergence(self):
        self.assertEqual(
            module.diagnostic_label(
                {"prediction_mismatch_count": 2},
                {"prediction_mismatch_count": 4},
            ),
            "W4_DOES_NOT_EXPLAIN_BUILT_DIVERGENCE",
        )


if __name__ == "__main__":
    unittest.main()
