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

FRAMING_RUNNER = ROOT / "scripts" / "run_framing_probe.py"
FRAMING_RECEIPT = ROOT / "scripts" / "framing_probe_receipt.py"
FRAMING_WORKFLOW = ROOT / ".github" / "workflows" / "needle-framing-2x2.yml"


class FramingProbeContractTest(unittest.TestCase):
    def test_schema_and_query_factors_form_exact_two_by_two(self):
        self.assertTrue(FRAMING_RUNNER.is_file())
        module = load_module("run_framing_probe_contract", FRAMING_RUNNER)
        arms = module.arm_specs()
        self.assertEqual(set(arms), {"A", "B", "C", "D"})
        self.assertEqual(arms["A"], {"described_schema": False, "explicit_prefix": False})
        self.assertEqual(arms["B"], {"described_schema": False, "explicit_prefix": True})
        self.assertEqual(arms["C"], {"described_schema": True, "explicit_prefix": False})
        self.assertEqual(arms["D"], {"described_schema": True, "explicit_prefix": True})

        bare = module.route_schema(False)
        described = module.route_schema(True)
        self.assertNotIn("description", bare)
        self.assertIn("Always use route for this classification", described["description"])
        self.assertEqual(bare["parameters"], described["parameters"])

        q = "Evidence statement."
        self.assertEqual(module.frame_query(q, False), q)
        self.assertEqual(
            module.frame_query(q, True),
            "Use route to classify the following evidence:\n\nEvidence statement.",
        )

    def test_direct_canaries_use_bare_schema_and_cover_all_three_decisions(self):
        self.assertTrue(FRAMING_RUNNER.is_file())
        module = load_module("run_framing_probe_canaries", FRAMING_RUNNER)
        self.assertEqual(module.canary_cases(), [
            {"id": "canary-PROBE", "query": "Call route with decision PROBE.", "expected": "PROBE"},
            {"id": "canary-READY", "query": "Call route with decision READY.", "expected": "READY"},
            {"id": "canary-UNKNOWN", "query": "Call route with decision UNKNOWN.", "expected": "UNKNOWN"},
        ])
        self.assertNotIn("description", module.route_schema(False))

    def test_workflow_runs_base_only_and_never_trains_or_loads_tuned_weights(self):
        self.assertTrue(FRAMING_WORKFLOW.is_file())
        text = FRAMING_WORKFLOW.read_text()
        self.assertIn("experiment/needle-framing-2x2", text)
        self.assertIn('cactus-needle==2.0.8', text)
        self.assertIn("experiments/needle-cpu-smoke/data.jsonl", text)
        self.assertIn("run_framing_probe.py", text)
        self.assertIn("framing_probe_receipt.py", text)
        self.assertIn("--max-new-tokens 256", text)
        self.assertNotIn("needle finetune", text)
        self.assertNotIn("needle build", text)
        self.assertNotIn("--weights", text)
        self.assertNotIn("secrets.", text)


class FramingProbeReceiptTest(unittest.TestCase):
    def test_receipt_separates_call_reachability_from_decision_accuracy(self):
        self.assertTrue(FRAMING_RECEIPT.is_file())
        module = load_module("framing_probe_receipt_contract", FRAMING_RECEIPT)
        canaries = [
            {"id": "canary-PROBE", "expected": "PROBE", "predicted": "PROBE", "valid_route_call": True, "correct": True},
            {"id": "canary-READY", "expected": "READY", "predicted": "READY", "valid_route_call": True, "correct": True},
            {"id": "canary-UNKNOWN", "expected": "UNKNOWN", "predicted": "UNKNOWN", "valid_route_call": True, "correct": True},
        ]
        arms = {
            "A": [
                {"id": "train-001", "expected": "PROBE", "predicted": "NO_CALL", "valid_route_call": False, "correct": False},
                {"id": "train-002", "expected": "READY", "predicted": "READY", "valid_route_call": True, "correct": True},
            ],
            "B": [
                {"id": "train-001", "expected": "PROBE", "predicted": "PROBE", "valid_route_call": True, "correct": True},
                {"id": "train-002", "expected": "READY", "predicted": "UNKNOWN", "valid_route_call": True, "correct": False},
            ],
            "C": [
                {"id": "train-001", "expected": "PROBE", "predicted": "PROBE", "valid_route_call": True, "correct": True},
                {"id": "train-002", "expected": "READY", "predicted": "READY", "valid_route_call": True, "correct": True},
            ],
            "D": [
                {"id": "train-001", "expected": "PROBE", "predicted": "PROBE", "valid_route_call": True, "correct": True},
                {"id": "train-002", "expected": "READY", "predicted": "READY", "valid_route_call": True, "correct": True},
            ],
        }
        receipt = module.build_receipt(canaries, arms, commit="c" * 40, run_id="123")
        self.assertTrue(receipt["canaries"]["all_pass"])
        self.assertEqual(receipt["arms"]["A"]["valid_call_rate"], 0.5)
        self.assertEqual(receipt["arms"]["A"]["decision_accuracy"], 0.5)
        self.assertEqual(receipt["arms"]["B"]["valid_call_rate"], 1.0)
        self.assertEqual(receipt["arms"]["B"]["decision_accuracy"], 0.5)
        self.assertEqual(receipt["effects"]["call_rate"]["prefix_with_bare_schema"], 0.5)
        self.assertEqual(receipt["effects"]["call_rate"]["description_without_prefix"], 0.5)
        self.assertEqual(receipt["effects"]["decision_accuracy"]["prefix_with_bare_schema"], 0.0)
        self.assertEqual(receipt["interpretation_boundary"], "descriptive_zero_training_probe_not_statistical_significance")

VERBALIZER_RUNNER = ROOT / "scripts" / "run_verbalizer_factorized_probe.py"
VERBALIZER_RECEIPT = ROOT / "scripts" / "verbalizer_factorized_receipt.py"
VERBALIZER_WORKFLOW = ROOT / ".github" / "workflows" / "needle-verbalizer-factorized.yml"


class VerbalizerFactorizedProbeContractTest(unittest.TestCase):
    def test_flat_arm_a_is_exact_accepted_issue12_framing_and_other_arms_change_only_verbalizer(self):
        self.assertTrue(VERBALIZER_RUNNER.is_file())
        module = load_module("verbalizer_factorized_runner_flat", VERBALIZER_RUNNER)
        prior = load_module("verbalizer_factorized_prior", FRAMING_RUNNER)

        self.assertEqual(module.flat_schema("A"), prior.route_schema(True))
        self.assertEqual(module.frame_query("Evidence statement."), prior.frame_query("Evidence statement.", True))
        self.assertEqual(module.flat_specs()["A"]["labels"], ["PROBE", "READY", "UNKNOWN"])
        self.assertEqual(module.flat_specs()["B"]["labels"], ["probe", "ready", "unknown"])
        self.assertEqual(module.flat_specs()["C"]["labels"], ["A", "B", "C"])
        self.assertEqual(module.flat_specs()["C"]["to_decision"], {"A": "PROBE", "B": "READY", "C": "UNKNOWN"})

        for arm in "ABC":
            schema = module.flat_schema(arm)
            self.assertEqual(list(schema), ["name", "parameters", "description"])
            self.assertEqual(schema["name"], "route")
            self.assertEqual(list(schema["parameters"]["properties"]), ["decision"])
            self.assertIn("PROBE", schema["description"])
            self.assertIn("READY", schema["description"])
            self.assertIn("UNKNOWN", schema["description"])

    def test_factorized_truth_table_matches_project_policy(self):
        self.assertTrue(VERBALIZER_RUNNER.is_file())
        module = load_module("verbalizer_factorized_runner_truth", VERBALIZER_RUNNER)
        self.assertEqual(module.factorized_final("verified", None), "READY")
        self.assertEqual(module.factorized_final("insufficient", "available"), "PROBE")
        self.assertEqual(module.factorized_final("insufficient", "unavailable"), "UNKNOWN")
        self.assertEqual(module.expected_factorized("READY"), ("verified", None))
        self.assertEqual(module.expected_factorized("PROBE"), ("insufficient", "available"))
        self.assertEqual(module.expected_factorized("UNKNOWN"), ("insufficient", "unavailable"))
        self.assertEqual(list(module.evidence_schema()), ["name", "parameters", "description"])
        self.assertEqual(list(module.probe_schema()), ["name", "parameters", "description"])

    def test_records_exact_serialized_schema_and_framed_query_for_every_arm(self):
        self.assertTrue(VERBALIZER_RUNNER.is_file())
        text = VERBALIZER_RUNNER.read_text()
        self.assertIn('"schema_json"', text)
        self.assertIn('"framed_query"', text)
        self.assertIn('separators=(",", ":")', text)
        self.assertIn("ensure_ascii=False", text)

    def test_workflow_is_zero_training_and_runs_exact_four_representations(self):
        self.assertTrue(VERBALIZER_WORKFLOW.is_file())
        text = VERBALIZER_WORKFLOW.read_text()
        self.assertIn("experiment/needle-verbalizer-factorized", text)
        self.assertIn('cactus-needle==2.0.8', text)
        self.assertIn("experiments/needle-cpu-smoke/data.jsonl", text)
        for arm in "ABCD":
            self.assertIn(f"--arm {arm}", text)
            self.assertIn(f"results/arm-{arm.lower()}.jsonl", text)
        self.assertNotIn("needle finetune", text)
        self.assertNotIn("needle build", text)
        self.assertNotIn("--weights", text)
        self.assertNotIn("secrets.", text)


class VerbalizerFactorizedReceiptContractTest(unittest.TestCase):
    def test_receipt_scores_final_mapping_distribution_and_factorized_stages(self):
        self.assertTrue(VERBALIZER_RECEIPT.is_file())
        module = load_module("verbalizer_factorized_receipt_contract", VERBALIZER_RECEIPT)
        flat = [
            {"id": "x1", "expected": "PROBE", "predicted": "PROBE", "valid_structured_call": True, "correct": True},
            {"id": "x2", "expected": "READY", "predicted": "UNKNOWN", "valid_structured_call": True, "correct": False},
            {"id": "x3", "expected": "UNKNOWN", "predicted": "NO_CALL", "valid_structured_call": False, "correct": False},
        ]
        factorized = [
            {"id": "x1", "expected": "PROBE", "predicted": "PROBE", "valid_structured_call": True, "correct": True,
             "stage1_expected": "insufficient", "stage1_predicted": "insufficient", "stage1_valid": True,
             "stage2_expected": "available", "stage2_predicted": "available", "stage2_valid": True},
            {"id": "x2", "expected": "READY", "predicted": "READY", "valid_structured_call": True, "correct": True,
             "stage1_expected": "verified", "stage1_predicted": "verified", "stage1_valid": True,
             "stage2_expected": None, "stage2_predicted": None, "stage2_valid": None},
            {"id": "x3", "expected": "UNKNOWN", "predicted": "READY", "valid_structured_call": True, "correct": False,
             "stage1_expected": "insufficient", "stage1_predicted": "verified", "stage1_valid": True,
             "stage2_expected": "unavailable", "stage2_predicted": None, "stage2_valid": None},
        ]
        receipt = module.build_receipt(
            {"A": flat, "B": flat, "C": flat, "D": factorized},
            commit="c" * 40,
            run_id="123",
        )
        self.assertEqual(receipt["schema"], "theseus.needle.verbalizer_factorized_probe.v1")
        self.assertEqual(receipt["arms"]["A"]["decision_accuracy"], 1 / 3)
        self.assertEqual(receipt["arms"]["A"]["valid_call_rate"], 2 / 3)
        self.assertEqual(receipt["arms"]["A"]["prediction_distribution"], {"NO_CALL": 1, "PROBE": 1, "UNKNOWN": 1})
        self.assertEqual(receipt["arms"]["D"]["decision_accuracy"], 2 / 3)
        self.assertEqual(receipt["arms"]["D"]["stage1_accuracy"], 2 / 3)
        self.assertEqual(receipt["arms"]["D"]["stage2_expected_n"], 2)
        self.assertEqual(receipt["arms"]["D"]["stage2_attempted_n"], 1)
        self.assertEqual(receipt["interpretation_boundary"], "descriptive_zero_training_representation_probe_not_statistical_significance")

class VerbalizerFactorizedToolApplicabilityRegressionTest(unittest.TestCase):
    def test_factorized_stages_preserve_route_tool_name_and_explicit_route_prefix(self):
        module = load_module("verbalizer_factorized_route_regression", VERBALIZER_RUNNER)
        evidence = module.evidence_schema()
        probe = module.probe_schema()
        self.assertEqual(evidence["name"], "route")
        self.assertEqual(probe["name"], "route")
        self.assertEqual(list(evidence["parameters"]["properties"]), ["decision"])
        self.assertEqual(list(probe["parameters"]["properties"]), ["decision"])
        self.assertIn("Use route", module.evidence_query("Evidence statement."))
        self.assertIn("Use route", module.probe_query("Evidence statement."))

PERM_RUNNER = ROOT / "scripts" / "run_verbalizer_permutation_probe.py"
PERM_RECEIPT = ROOT / "scripts" / "verbalizer_permutation_receipt.py"
PERM_WORKFLOW = ROOT / ".github" / "workflows" / "needle-verbalizer-permutations.yml"


class VerbalizerPermutationProbeContractTest(unittest.TestCase):
    def test_all_six_bijections_are_present_once(self):
        self.assertTrue(PERM_RUNNER.is_file())
        module = load_module("run_verbalizer_permutation_contract", PERM_RUNNER)
        specs = module.permutation_specs()
        self.assertEqual(list(specs), ["P1", "P2", "P3", "P4", "P5", "P6"])
        mappings = []
        for spec in specs.values():
            self.assertEqual(spec["labels"], ["A", "B", "C"])
            mapping = spec["to_decision"]
            self.assertEqual(set(mapping), {"A", "B", "C"})
            self.assertEqual(set(mapping.values()), {"PROBE", "READY", "UNKNOWN"})
            mappings.append(tuple(mapping[x] for x in "ABC"))
        self.assertEqual(len(set(mappings)), 6)

    def test_p1_is_exact_predecessor_one_token_contract(self):
        self.assertTrue(PERM_RUNNER.is_file())
        current = load_module("run_verbalizer_permutation_p1", PERM_RUNNER)
        predecessor = load_module("run_verbalizer_factorized_p1", ROOT / "scripts" / "run_verbalizer_factorized_probe.py")
        p1 = current.permutation_specs()["P1"]
        self.assertEqual(p1["to_decision"], {"A": "PROBE", "B": "READY", "C": "UNKNOWN"})
        self.assertEqual(current.PREFIX, predecessor.PREFIX)
        self.assertEqual(
            current.serialize_schema(current.route_schema("P1")),
            predecessor.serialize_schema(predecessor.flat_schema("C")),
        )

    def test_records_raw_token_and_mapped_decision_separately(self):
        self.assertTrue(PERM_RUNNER.is_file())
        text = PERM_RUNNER.read_text()
        self.assertIn('"predicted_token": raw_label', text)
        self.assertIn('"predicted": predicted', text)
        self.assertIn('"schema_json": schema_json', text)
        self.assertIn('"framed_query": query', text)

    def test_workflow_is_base_only_and_runs_exactly_six_mappings(self):
        self.assertTrue(PERM_WORKFLOW.is_file())
        text = PERM_WORKFLOW.read_text()
        self.assertIn("cactus-needle==2.0.8", text)
        for name in ["P1", "P2", "P3", "P4", "P5", "P6"]:
            self.assertEqual(text.count(f"--mapping {name}"), 1)
        self.assertNotIn("needle finetune", text)
        self.assertNotIn("needle build", text)
        self.assertNotIn("--weights", text)
        self.assertNotIn("secrets.", text)


class VerbalizerPermutationReceiptContractTest(unittest.TestCase):
    def test_receipt_measures_raw_token_stability_separately_from_semantic_accuracy(self):
        self.assertTrue(PERM_RECEIPT.is_file())
        module = load_module("verbalizer_permutation_receipt_contract", PERM_RECEIPT)
        arms = {}
        maps = [
            {"A": "PROBE", "B": "READY", "C": "UNKNOWN"},
            {"A": "PROBE", "B": "UNKNOWN", "C": "READY"},
            {"A": "READY", "B": "PROBE", "C": "UNKNOWN"},
            {"A": "READY", "B": "UNKNOWN", "C": "PROBE"},
            {"A": "UNKNOWN", "B": "PROBE", "C": "READY"},
            {"A": "UNKNOWN", "B": "READY", "C": "PROBE"},
        ]
        for idx, mapping in enumerate(maps, start=1):
            token1 = "A"
            token2 = "ABC"[(idx - 1) % 3]
            arms[f"P{idx}"] = [
                {"id": "x1", "expected": "PROBE", "predicted_token": token1,
                 "predicted": mapping[token1], "valid_structured_call": True,
                 "correct": mapping[token1] == "PROBE"},
                {"id": "x2", "expected": "READY", "predicted_token": token2,
                 "predicted": mapping[token2], "valid_structured_call": True,
                 "correct": mapping[token2] == "READY"},
            ]
        receipt = module.build_receipt(arms, commit="c" * 40, run_id="123")
        self.assertEqual(receipt["schema"], "theseus.needle.verbalizer_permutation_probe.v1")
        self.assertEqual(receipt["raw_token_stability"]["all_mapping_same_n"], 1)
        self.assertEqual(receipt["raw_token_stability"]["n"], 2)
        self.assertEqual(receipt["raw_token_stability"]["all_mapping_same_rate"], 0.5)
        self.assertIn("raw_token_distribution", receipt["arms"]["P1"])
        self.assertIn("decision_accuracy", receipt["arms"]["P1"])
        self.assertEqual(receipt["interpretation_boundary"], "descriptive_zero_training_permutation_probe_not_statistical_significance")


SEMANTIC_PREFLIGHT_RUNNER = ROOT / "scripts" / "run_semantic_verbalizer_preflight.py"
SEMANTIC_PREFLIGHT_RECEIPT = ROOT / "scripts" / "semantic_verbalizer_preflight_receipt.py"
SEMANTIC_PREFLIGHT_WORKFLOW = ROOT / ".github" / "workflows" / "needle-semantic-verbalizer-preflight.yml"
SEMANTIC_PREFLIGHT_README = ROOT / "experiments" / "needle-semantic-verbalizer-preflight" / "README.md"


class SemanticVerbalizerPreflightContractTest(unittest.TestCase):
    def test_three_arms_preserve_predecessor_a_b_and_add_semantic_check_arm(self):
        self.assertTrue(SEMANTIC_PREFLIGHT_RUNNER.is_file())
        current = load_module("semantic_verbalizer_preflight_runner", SEMANTIC_PREFLIGHT_RUNNER)
        predecessor = load_module("semantic_verbalizer_predecessor", ROOT / "scripts" / "run_verbalizer_factorized_probe.py")
        specs = current.arm_specs()
        self.assertEqual(list(specs), ["A", "B", "C"])
        self.assertEqual(specs["A"], predecessor.flat_specs()["A"])
        self.assertEqual(specs["B"], predecessor.flat_specs()["B"])
        self.assertEqual(specs["C"]["labels"], ["check", "ready", "unknown"])
        self.assertEqual(
            specs["C"]["to_decision"],
            {"check": "PROBE", "ready": "READY", "unknown": "UNKNOWN"},
        )
        self.assertEqual(current.PREFIX, predecessor.PREFIX)
        for arm in "AB":
            self.assertEqual(
                current.serialize_schema(current.route_schema(arm)),
                predecessor.serialize_schema(predecessor.flat_schema(arm)),
            )

    def test_records_exact_prompt_contract_raw_label_and_label_tokenization(self):
        self.assertTrue(SEMANTIC_PREFLIGHT_RUNNER.is_file())
        text = SEMANTIC_PREFLIGHT_RUNNER.read_text()
        self.assertIn('"predicted_label": raw_label', text)
        self.assertIn('"predicted": predicted', text)
        self.assertIn('"schema_json": schema_json', text)
        self.assertIn('"framed_query": query', text)
        self.assertIn('"label_tokenization": label_tokenization', text)

    def test_workflow_is_base_only_exact_three_arms_and_asserts_predecessor_identity(self):
        self.assertTrue(SEMANTIC_PREFLIGHT_WORKFLOW.is_file())
        text = SEMANTIC_PREFLIGHT_WORKFLOW.read_text()
        self.assertIn("experiment/needle-semantic-verbalizer-preflight", text)
        self.assertIn('cactus-needle==2.0.8', text)
        self.assertIn("Assert exact A/B predecessor contracts", text)
        for arm in "ABC":
            self.assertEqual(text.count(f"--arm {arm}"), 1)
            self.assertIn(f"results/arm-{arm.lower()}.jsonl", text)
        self.assertNotIn("needle finetune", text)
        self.assertNotIn("needle build", text)
        self.assertNotIn("--weights", text)
        self.assertNotIn("secrets.", text)

    def test_readme_declares_interface_selection_not_learning_claim(self):
        self.assertTrue(SEMANTIC_PREFLIGHT_README.is_file())
        text = SEMANTIC_PREFLIGHT_README.read_text()
        self.assertIn("#26", text)
        self.assertIn("zero-training", text.lower())
        self.assertIn("interface prior", text.lower())
        self.assertIn("not evidence of learned policy", text.lower())


class SemanticVerbalizerPreflightReceiptContractTest(unittest.TestCase):
    def test_receipt_scores_accuracy_applicability_and_collapse_separately(self):
        self.assertTrue(SEMANTIC_PREFLIGHT_RECEIPT.is_file())
        module = load_module("semantic_verbalizer_preflight_receipt", SEMANTIC_PREFLIGHT_RECEIPT)
        arms = {
            "A": [
                {"id": "x1", "expected": "PROBE", "predicted_label": "PROBE", "predicted": "PROBE", "valid_structured_call": True, "correct": True},
                {"id": "x2", "expected": "READY", "predicted_label": "NO_CALL", "predicted": "NO_CALL", "valid_structured_call": False, "correct": False},
                {"id": "x3", "expected": "UNKNOWN", "predicted_label": "UNKNOWN", "predicted": "UNKNOWN", "valid_structured_call": True, "correct": True},
            ],
            "B": [
                {"id": "x1", "expected": "PROBE", "predicted_label": "probe", "predicted": "PROBE", "valid_structured_call": True, "correct": True},
                {"id": "x2", "expected": "READY", "predicted_label": "probe", "predicted": "PROBE", "valid_structured_call": True, "correct": False},
                {"id": "x3", "expected": "UNKNOWN", "predicted_label": "probe", "predicted": "PROBE", "valid_structured_call": True, "correct": False},
            ],
            "C": [
                {"id": "x1", "expected": "PROBE", "predicted_label": "check", "predicted": "PROBE", "valid_structured_call": True, "correct": True},
                {"id": "x2", "expected": "READY", "predicted_label": "ready", "predicted": "READY", "valid_structured_call": True, "correct": True},
                {"id": "x3", "expected": "UNKNOWN", "predicted_label": "unknown", "predicted": "UNKNOWN", "valid_structured_call": True, "correct": True},
            ],
        }
        receipt = module.build_receipt(arms, commit="c" * 40, run_id="123")
        self.assertEqual(receipt["schema"], "theseus.needle.semantic_verbalizer_preflight.v1")
        self.assertEqual(receipt["arms"]["A"]["valid_call_rate"], 2 / 3)
        self.assertEqual(receipt["arms"]["A"]["decision_accuracy"], 2 / 3)
        self.assertEqual(receipt["arms"]["B"]["dominant_prediction"], "PROBE")
        self.assertEqual(receipt["arms"]["B"]["dominant_prediction_rate"], 1.0)
        self.assertTrue(receipt["arms"]["B"]["collapsed"])
        self.assertFalse(receipt["arms"]["C"]["collapsed"])
        self.assertEqual(receipt["arms"]["C"]["decision_accuracy"], 1.0)
        self.assertEqual(
            receipt["interpretation_boundary"],
            "zero_training_interface_prior_selection_not_evidence_of_learned_policy",
        )
