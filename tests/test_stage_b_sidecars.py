import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class StageBAcceptanceSidecarTest(unittest.TestCase):
    def test_local_acceptance_canary_matches_preregistered_integer_rules(self):
        from scripts.stage_b_acceptance_sidecar import evaluate_acceptance

        result = evaluate_acceptance({
            "base_heldout_correct": 30,
            "replica_heldout_correct": 38,
            "train_correct": 225,
            "train_total": 300,
            "base_route_calls": 60,
            "replica_route_calls": 58,
            "base_negative_no_call": 22,
            "replica_negative_no_call": 21,
            "dominant_decision_count": 40,
            "valid_heldout_route_calls": 60,
        })
        self.assertTrue(result["all_pass"])
        self.assertEqual(result["heldout_improvement_count"], 8)
        self.assertEqual(result["train_accuracy_fraction"], "3/4")
        self.assertEqual(result["dominant_fraction"], "2/3")
        self.assertEqual(set(result["checks"]), {
            "heldout_improvement", "train_accuracy", "reachability_degradation",
            "negative_no_call_degradation", "dominant_decision_cap",
        })

    def test_special_functions_lane_is_not_applicable_to_current_acceptance_claim(self):
        from scripts.stage_b_acceptance_sidecar import classify_special_functions_applicability

        claim = json.loads((ROOT / "experiments/needle-realistic-sft/verification/stage-b-acceptance-canary.json").read_text())
        result = classify_special_functions_applicability(claim)
        self.assertEqual(result["disposition"], "NOT_APPLICABLE")
        self.assertEqual(result["required_special_functions"], [])

    def test_scipy_sidecar_is_diagnostic_not_acceptance_authority(self):
        text = (ROOT / "scripts/stage_b_scipy_diagnostics.py").read_text()
        self.assertIn("from scipy.stats import fisher_exact", text)
        self.assertIn('"authority": "DIAGNOSTIC_ONLY"', text)
        self.assertNotIn("ACCEPTED_LEARNED_AND_GENERALIZES", text)


if __name__ == "__main__":
    unittest.main()

class StageBSidecarWorkflowContractTest(unittest.TestCase):
    def test_workflow_is_read_only_pins_scipy_and_wolfram_client_and_never_trains(self):
        text = (ROOT / ".github/workflows/needle-stage-b-sidecar-canary.yml").read_text()
        self.assertIn("contents: read", text)
        self.assertIn('python-version: "3.12"', text)
        self.assertIn("scipy==1.18.1", text)
        self.assertIn("npm ci --ignore-scripts --prefix verification/stage-b-sidecars/wolfram", text)
        self.assertIn("stage_b_wolfram_canary.mjs", text)
        self.assertIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02", text)
        self.assertNotIn("run_seeded_finetune", text)
        self.assertNotIn("needle finetune", text)

    def test_wolfram_canary_binds_raw_transport_and_normalized_result(self):
        text = (ROOT / "scripts/stage_b_wolfram_canary.mjs").read_text()
        self.assertIn("raw_transport_sha256", text)
        self.assertIn("normalized_result", text)
        self.assertIn("mcporter@0.9.0", text)
        self.assertIn("node_modules/.bin/mcporter", text)
        self.assertIn("WolframLanguageEvaluator", text)
