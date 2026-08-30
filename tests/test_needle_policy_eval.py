import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASES = ROOT / "experiments" / "needle-policy-eval" / "cases.jsonl"
RUNNER = ROOT / "scripts" / "run_policy_eval.py"
COMPARE = ROOT / "scripts" / "compare_policy_eval.py"
WORKFLOW = ROOT / ".github" / "workflows" / "needle-policy-eval.yml"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PolicyEvalContractTest(unittest.TestCase):
    def test_cases_are_balanced_held_out_and_include_negative_controls(self):
        rows = [json.loads(line) for line in CASES.read_text().splitlines() if line.strip()]
        self.assertEqual(len(rows), 24)
        self.assertEqual(len({row["id"] for row in rows}), 24)
        self.assertEqual({k: sum(row["expected"] == k for row in rows) for k in ["PROBE", "READY", "UNKNOWN", "NO_CALL"]}, {
            "PROBE": 6, "READY": 6, "UNKNOWN": 6, "NO_CALL": 6,
        })
        self.assertEqual({k: sum(row["category"] == k for row in rows) for k in ["paraphrase", "unseen_harness", "verification_boundary", "negative_control"]}, {
            "paraphrase": 6, "unseen_harness": 6, "verification_boundary": 6, "negative_control": 6,
        })
        for row in rows:
            self.assertEqual(set(row), {"id", "category", "query", "expected"})
            self.assertTrue(row["query"].strip())

    def test_response_classifier_is_strict_and_does_not_use_confidence(self):
        module = load_module("run_policy_eval", RUNNER)
        self.assertEqual(module.classify_response({"type": "text", "confidence": 0.99}), "NO_CALL")
        self.assertEqual(module.classify_response({
            "type": "call", "confidence": 0.01,
            "function_calls": [{"name": "route", "arguments": {"decision": "PROBE"}}],
        }), "PROBE")
        self.assertEqual(module.classify_response({
            "type": "call", "confidence": None,
            "function_calls": [{"name": "route", "arguments": {"decision": "READY"}}],
        }), "READY")
        self.assertEqual(module.classify_response({
            "type": "call", "function_calls": [{"name": "route", "arguments": {"decision": "UNKNOWN"}}],
        }), "UNKNOWN")
        self.assertEqual(module.classify_response({
            "type": "call", "function_calls": [{"name": "route", "arguments": {"decision": "MAYBE"}}],
        }), "INVALID")
        self.assertEqual(module.classify_response({
            "type": "call", "function_calls": [
                {"name": "route", "arguments": {"decision": "READY"}},
                {"name": "route", "arguments": {"decision": "READY"}},
            ],
        }), "INVALID")

    def test_summary_reports_base_tuned_delta_and_confusion(self):
        module = load_module("compare_policy_eval", COMPARE)
        base = [
            {"id": "a", "expected": "PROBE", "predicted": "READY", "correct": False},
            {"id": "b", "expected": "READY", "predicted": "READY", "correct": True},
            {"id": "c", "expected": "NO_CALL", "predicted": "NO_CALL", "correct": True},
        ]
        tuned = [
            {"id": "a", "expected": "PROBE", "predicted": "PROBE", "correct": True},
            {"id": "b", "expected": "READY", "predicted": "READY", "correct": True},
            {"id": "c", "expected": "NO_CALL", "predicted": "PROBE", "correct": False},
        ]
        summary = module.compare(base, tuned)
        self.assertAlmostEqual(summary["base"]["overall_accuracy"], 2 / 3)
        self.assertAlmostEqual(summary["tuned"]["overall_accuracy"], 2 / 3)
        self.assertEqual(summary["delta"]["overall_accuracy"], 0.0)
        self.assertEqual(summary["base"]["negative_control_no_call_rate"], 1.0)
        self.assertEqual(summary["tuned"]["negative_control_no_call_rate"], 0.0)
        self.assertEqual(summary["tuned"]["confusion"]["PROBE"]["PROBE"], 1)

    def test_workflow_uses_exact_prior_artifact_without_retraining(self):
        text = WORKFLOW.read_text()
        self.assertIn("experiment/needle-policy-eval", text)
        self.assertIn("actions: read", text)
        self.assertIn("contents: read", text)
        self.assertIn("run-id: 33319821037", text)
        self.assertIn("needle-cpu-smoke-33319821037", text)
        self.assertIn("d3f86a106a0bac45b974a628896c90dbdf5c8093", text)
        self.assertIn("3c0c684888c0d796e1b3a62326fbb1f3cc991f6ee5a0e596ac448df99edef10a", text)
        self.assertNotIn("needle finetune", text)
        self.assertNotIn("secrets.", text)
        self.assertIn("--model-id base", text)
        self.assertIn("--model-id tuned", text)


if __name__ == "__main__":
    unittest.main()
