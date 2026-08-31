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

class TrainReplayContractTest(unittest.TestCase):
    def test_training_loader_recovers_twelve_original_labels(self):
        module = load_module("run_policy_eval_train", RUNNER)
        rows = module.load_training_cases(ROOT / "experiments" / "needle-cpu-smoke" / "data.jsonl")
        self.assertEqual(len(rows), 12)
        self.assertEqual(len({row["id"] for row in rows}), 12)
        self.assertTrue(all(row["category"] == "training_replay" for row in rows))
        self.assertEqual({k: sum(row["expected"] == k for row in rows) for k in ["PROBE", "READY", "UNKNOWN"]}, {
            "PROBE": 4, "READY": 4, "UNKNOWN": 4,
        })

    def test_workflow_replays_training_set_without_finetuning(self):
        text = WORKFLOW.read_text()
        self.assertIn("--training-jsonl experiments/needle-cpu-smoke/data.jsonl", text)
        self.assertIn("results/train-base.jsonl", text)
        self.assertIn("results/train-tuned.jsonl", text)
        self.assertIn("results/train-replay-receipt.json", text)
        self.assertNotIn("needle finetune", text)

class CompareOptionalMetricTest(unittest.TestCase):
    def test_compare_keeps_negative_control_delta_null_when_metric_not_applicable(self):
        module = load_module("compare_policy_eval_optional", COMPARE)
        base = [{"id": "a", "category": "training_replay", "expected": "PROBE", "predicted": "PROBE", "correct": True}]
        tuned = [{"id": "a", "category": "training_replay", "expected": "PROBE", "predicted": "READY", "correct": False}]
        result = module.compare(base, tuned)
        self.assertIsNone(result["base"]["negative_control_no_call_rate"])
        self.assertIsNone(result["tuned"]["negative_control_no_call_rate"])
        self.assertIsNone(result["delta"]["negative_control_no_call_rate"])

class MarkdownOptionalMetricTest(unittest.TestCase):
    def test_markdown_renders_inapplicable_negative_control_metric_as_na(self):
        module = load_module("compare_policy_eval_markdown_optional", COMPARE)
        receipt = {"comparison": {
            "base": {"overall_accuracy": 0.5, "routing_accuracy": 0.5, "negative_control_no_call_rate": None},
            "tuned": {"overall_accuracy": 0.75, "routing_accuracy": 0.75, "negative_control_no_call_rate": None},
            "delta": {"overall_accuracy": 0.25, "routing_accuracy": 0.25, "negative_control_no_call_rate": None},
            "changed_predictions": [],
        }}
        text = module.markdown(receipt)
        self.assertIn("Base negative-control no-call rate: n/a", text)
        self.assertIn("Tuned negative-control no-call rate: n/a", text)
        self.assertIn("Delta negative-control no-call: n/a", text)

class DecodeBudgetContractTest(unittest.TestCase):
    def test_evaluator_uses_upstream_256_token_budget_and_records_it(self):
        runner_text = RUNNER.read_text()
        workflow_text = WORKFLOW.read_text()
        self.assertIn('parser.add_argument("--max-new-tokens", type=int, default=256)', runner_text)
        self.assertEqual(workflow_text.count("--max-new-tokens 256"), 5)
        module = load_module("compare_policy_eval_decode_budget", COMPARE)
        base = [{"id":"a","category":"x","expected":"READY","predicted":"READY","correct":True,"max_new_tokens":256}]
        tuned = [{"id":"a","category":"x","expected":"READY","predicted":"READY","correct":True,"max_new_tokens":256}]
        self.assertEqual(module.shared_max_new_tokens(base, tuned), 256)

    def test_mixed_decode_budgets_are_rejected(self):
        module = load_module("compare_policy_eval_mixed_budget", COMPARE)
        base = [{"id":"a","max_new_tokens":64}]
        tuned = [{"id":"a","max_new_tokens":256}]
        with self.assertRaises(ValueError):
            module.shared_max_new_tokens(base, tuned)

QUANT_RECEIPT = ROOT / "scripts" / "quantization_probe_receipt.py"

class QuantizationProbeContractTest(unittest.TestCase):
    def test_quantization_receipt_labels_mixed_and_w4_explicitly(self):
        module = load_module("quantization_probe_receipt", QUANT_RECEIPT)
        mixed = [{"id":"a","category":"training_replay","expected":"READY","predicted":"NO_CALL","correct":False,"max_new_tokens":256}]
        w4 = [{"id":"a","category":"training_replay","expected":"READY","predicted":"READY","correct":True,"max_new_tokens":256}]
        receipt = module.build_receipt(
            mixed, w4,
            checkpoint_sha256="c"*64,
            adapter_sha256="a"*64,
            mixed_sha256="m"*64,
            w4_sha256="w"*64,
            w4_size_bytes=123,
        )
        self.assertEqual(receipt["schema"], "theseus.needle.quantization_probe.v1")
        self.assertEqual(receipt["models"], {"base_field":"default_mixed", "tuned_field":"uniform_w4"})
        self.assertEqual(receipt["comparison"]["base"]["overall_accuracy"], 0.0)
        self.assertEqual(receipt["comparison"]["tuned"]["overall_accuracy"], 1.0)
        self.assertEqual(receipt["inputs"]["max_new_tokens"], 256)

    def test_workflow_builds_w4_from_exact_adapter_without_retraining(self):
        text = WORKFLOW.read_text()
        self.assertIn("7005de88bbe7fa9cfaa3e7cab90fc344e2b9e5e45f187f5b90c75cf0c8f9e7fc", text)
        self.assertIn("4b0a972d163ffc7678fb3c36bace508114872e9d2ce9e10f225825752d3795bc", text)
        self.assertIn("needle build checkpoints/needle2.pkl", text)
        self.assertIn("--lora input/smoke/artifacts/adapter.pkl", text)
        self.assertIn("--bits 4", text)
        self.assertIn("--out results/tuned-w4.cact", text)
        self.assertIn("--weights results/tuned-w4.cact", text)
        self.assertIn("results/quantization-receipt.json", text)
        self.assertNotIn("needle finetune", text)

SEEDED_FINETUNE = ROOT / "scripts" / "run_seeded_finetune.py"
TARGET_COVERAGE = ROOT / "scripts" / "target_coverage.py"
MAXLEN_WORKFLOW = ROOT / ".github" / "workflows" / "needle-maxlen-ab.yml"

class MaxLenABContractTest(unittest.TestCase):
    def test_seeded_wrapper_exists_and_seeds_numpy_before_finetune(self):
        self.assertTrue(SEEDED_FINETUNE.is_file())
        text = SEEDED_FINETUNE.read_text()
        self.assertIn("np.random.seed(args.seed)", text)
        self.assertIn("finetune_local(args)", text)
        self.assertIn("--seed", text)
        self.assertIn("--max-len", text)

    def test_target_coverage_math_detects_truncated_target(self):
        self.assertTrue(TARGET_COVERAGE.is_file())
        module = load_module("target_coverage", TARGET_COVERAGE)
        complete = module.coverage_record(prompt_tokens=80, target_tokens=40, cap=128)
        truncated = module.coverage_record(prompt_tokens=92, target_tokens=38, cap=128)
        self.assertTrue(complete["target_complete"])
        self.assertTrue(complete["eos_kept"])
        self.assertEqual(complete["target_tokens_retained"], 40)
        self.assertFalse(truncated["target_complete"])
        self.assertFalse(truncated["eos_kept"])
        self.assertEqual(truncated["target_tokens_retained"], 35)

    def test_workflow_is_paired_seeded_and_changes_only_max_len_between_training_arms(self):
        self.assertTrue(MAXLEN_WORKFLOW.is_file())
        text = MAXLEN_WORKFLOW.read_text()
        self.assertIn("experiment/needle-maxlen-ab", text)
        self.assertIn("cactus-needle==2.0.8", text)
        self.assertIn("4b0a972d163ffc7678fb3c36bace508114872e9d2ce9e10f225825752d3795bc", text)
        self.assertEqual(text.count("--seed 0"), 2)
        self.assertEqual(text.count("--epochs 1"), 2)
        self.assertEqual(text.count("--batch-size 2"), 2)
        self.assertEqual(text.count("--lr 1e-4"), 2)
        self.assertEqual(text.count("--lora-rank 4"), 2)
        self.assertEqual(text.count("--lora-alpha 32"), 2)
        self.assertEqual(text.count("--max-len 128"), 1)
        self.assertEqual(text.count("--max-len 1024"), 1)
        self.assertEqual(text.count("--bits 4"), 2)
        self.assertEqual(text.count("--max-new-tokens 256"), 4)
        self.assertIn("target_coverage.py", text)
        self.assertIn("assert_full_training_targets", text)
        self.assertNotIn("OpenRouter", text)
        self.assertNotIn("secrets.", text)

MAXLEN_RECEIPT = ROOT / "scripts" / "maxlen_ab_receipt.py"

class MaxLenABReceiptContractTest(unittest.TestCase):
    def test_receipt_records_both_artifacts_coverage_seed_and_train_delta(self):
        self.assertTrue(MAXLEN_RECEIPT.is_file())
        module = load_module("maxlen_ab_receipt", MAXLEN_RECEIPT)
        a = [{"id":"train-001","category":"training_replay","expected":"PROBE","predicted":"NO_CALL","correct":False,"max_new_tokens":256}]
        b = [{"id":"train-001","category":"training_replay","expected":"PROBE","predicted":"PROBE","correct":True,"max_new_tokens":256}]
        receipt = module.build_receipt(
            train_a=a,
            train_b=b,
            heldout_a=[],
            heldout_b=[],
            coverage_a={"effective_max_len":128,"summary":{"training_truncated_rows":[7,9,12]}},
            coverage_b={"effective_max_len":256,"summary":{"training_truncated_rows":[]}},
            adapter_a_sha256="a"*64,
            adapter_b_sha256="b"*64,
            cact_a_sha256="c"*64,
            cact_b_sha256="d"*64,
            seed=0,
        )
        self.assertEqual(receipt["schema"], "theseus.needle.maxlen_ab.v1")
        self.assertEqual(receipt["config"]["seed"], 0)
        self.assertEqual(receipt["arms"]["a"]["effective_max_len"], 128)
        self.assertEqual(receipt["arms"]["b"]["effective_max_len"], 256)
        self.assertEqual(receipt["arms"]["a"]["training_truncated_rows"], [7,9,12])
        self.assertEqual(receipt["arms"]["b"]["training_truncated_rows"], [])
        self.assertEqual(receipt["train_comparison"]["delta"]["overall_accuracy"], 1.0)
