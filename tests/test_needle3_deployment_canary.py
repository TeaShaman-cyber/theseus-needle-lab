import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "needle3_deployment_canary.py"
MANIFEST = ROOT / "experiments" / "needle3-deployment-canary" / "v1" / "manifest.json"

spec = importlib.util.spec_from_file_location("needle3_deployment_canary", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def response(prediction):
    if prediction == "NO_CALL":
        return {"type": "text", "function_calls": []}
    if prediction == "INVALID":
        return {
            "type": "call",
            "function_calls": [{"name": "wrong_tool", "arguments": {}}],
        }
    return {
        "type": "call",
        "function_calls": [{"name": "route", "arguments": {"decision": prediction}}],
    }


class Needle3DeploymentCanaryTests(unittest.TestCase):
    def setUp(self):
        self.manifest = module.load_json(MANIFEST)
        self.cases = module.validate_manifest(self.manifest, MANIFEST)

    def rows(self, surface, predictions=None):
        if predictions is None:
            predictions = [case["expected"] for case in self.cases]
        responses = [(response(pred), float(i + 1)) for i, pred in enumerate(predictions)]
        return module._result_rows(self.cases, surface, responses)

    def provenance(self, surface, *, adapter="b" * 64):
        snap = self.manifest["upstream_snapshot"]
        assets = self.manifest["published_runtime_assets"]
        checkpoint = assets["base_checkpoint"]
        value = {
            "schema_version": "theseus.needle3.surface_provenance.v1",
            "surface": surface,
            "source_commit": snap["source_commit"],
            "release_tag": snap["release_tag"],
            "release_tag_commit": snap["release_tag_commit"],
            "package_version": snap["package_version"],
            "wheel_filename": snap["wheel_filename"],
            "wheel_sha256": snap["wheel_sha256"],
            "fixture_sha256": self.manifest["fixture"]["sha256"],
            "base_checkpoint_sha256": checkpoint["sha256"],
            "base_checkpoint_size_bytes": checkpoint["size_bytes"],
        }
        if surface in {"lora_reference", "built_cact"}:
            value["lora_adapter_sha256"] = adapter
        if surface == "built_cact":
            engine = assets["engine"]
            base_cact = assets["published_base_cact"]
            value.update(
                {
                    "built_cact_sha256": "c" * 64,
                    "engine_version": engine["version"],
                    "engine_platform_tag": engine["platform_tag"],
                    "engine_binary_sha256": engine["binary_sha256"],
                    "engine_binary_size_bytes": engine["binary_size_bytes"],
                    "published_base_cact_sha256": base_cact["sha256"],
                    "published_base_cact_size_bytes": base_cact["size_bytes"],
                }
            )
        return value

    def test_frozen_fixture_geometry_and_no_call_negatives(self):
        self.assertEqual(len(self.cases), 12)
        expected = [case["expected"] for case in self.cases]
        self.assertEqual(expected.count("PROBE"), 2)
        self.assertEqual(expected.count("READY"), 2)
        self.assertEqual(expected.count("UNKNOWN"), 2)
        self.assertEqual(expected.count("NO_CALL"), 6)
        negatives = [case for case in self.cases if case["expected"] == "NO_CALL"]
        self.assertTrue(all(case["answers"] == [] for case in negatives))

    def test_training_fixture_is_small_balanced_and_disjoint_from_eval(self):
        training = module.load_jsonl(
            ROOT / self.manifest["training_fixture"]["path"]
        )
        self.assertEqual(len(training), 48)
        counts = {}
        for row in training:
            counts[row["_canary_expected"]] = counts.get(row["_canary_expected"], 0) + 1
        self.assertEqual(
            counts,
            {"PROBE": 12, "READY": 12, "UNKNOWN": 12, "NO_CALL": 12},
        )
        self.assertTrue(
            {row["_canary_case_id"] for row in training}.isdisjoint(
                {case["case_id"] for case in self.cases}
            )
        )

    def test_reference_text_parser_preserves_call_and_no_call(self):
        call = module.reference_text_to_response(
            '<tool_call>[{"name":"route","arguments":{"decision":"READY"}}]</tool_call>'
        )
        self.assertEqual(module.classify_response(call), "READY")

        no_call = module.reference_text_to_response("<tool_call>[]</tool_call>")
        self.assertEqual(module.classify_response(no_call), "NO_CALL")

        malformed = module.reference_text_to_response("<tool_call>{broken}</tool_call>")
        self.assertEqual(module.classify_response(malformed), "INVALID")
        self.assertEqual(malformed["type"], "invalid")

        empty_call = {"type": "call", "function_calls": []}
        self.assertEqual(module.classify_response(empty_call), "INVALID")

    def test_reference_parser_rejects_multiple_tool_call_blocks(self):
        value = module.reference_text_to_response(
            '<tool_call>[{"name":"route","arguments":{"decision":"READY"}}]</tool_call>'
            '<tool_call>[{"name":"route","arguments":{"decision":"PROBE"}}]</tool_call>'
        )
        self.assertEqual(module.classify_response(value), "INVALID")
        self.assertEqual(
            value["parse_error"],
            "multiple_or_unbalanced_tool_call_blocks",
        )

    def test_reference_parser_rejects_second_empty_tool_call_block(self):
        value = module.reference_text_to_response(
            '<tool_call>[{"name":"route","arguments":{"decision":"READY"}}]</tool_call>'
            '<tool_call>[]</tool_call>'
        )
        self.assertEqual(module.classify_response(value), "INVALID")
        self.assertEqual(
            value["parse_error"],
            "multiple_or_unbalanced_tool_call_blocks",
        )

    def test_reference_parser_rejects_orphan_tool_call_delimiter(self):
        value = module.reference_text_to_response("answer</tool_call>")
        self.assertEqual(module.classify_response(value), "INVALID")
        self.assertEqual(
            value["parse_error"],
            "multiple_or_unbalanced_tool_call_blocks",
        )

    def test_surface_rows_bind_exact_case_input(self):
        rows = self.rows("base_reference")
        module.validate_surface_rows(self.cases, rows, "base_reference")
        changed = copy.deepcopy(rows)
        changed[0]["case_input_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "input binding"):
            module.validate_surface_rows(self.cases, changed, "base_reference")

    def test_surface_metrics_keep_correctness_reachability_no_call_and_collapse_separate(self):
        rows = self.rows("base_reference")
        metrics = module.surface_metrics(rows)
        self.assertEqual(metrics["positive_n"], 6)
        self.assertEqual(metrics["positive_correct"], 6)
        self.assertEqual(metrics["positive_route_calls"], 6)
        self.assertEqual(metrics["negative_n"], 6)
        self.assertEqual(metrics["negative_no_call"], 6)
        self.assertEqual(metrics["negative_false_call"], 0)
        self.assertEqual(metrics["invalid_predictions"], 0)
        self.assertAlmostEqual(metrics["dominant_positive_decision_rate"], 2 / 6)

    def test_disposition_no_current_signal_when_surfaces_match(self):
        base = self.rows("base_reference")
        lora = self.rows("lora_reference")
        built = self.rows("built_cact")
        metrics = {
            "base_reference": module.surface_metrics(base),
            "lora_reference": module.surface_metrics(lora),
            "built_cact": module.surface_metrics(built),
        }
        divergence = module.pairwise_divergence(lora, built)
        disposition, reasons = module.decide(
            self.manifest,
            metrics["base_reference"],
            metrics["lora_reference"],
            metrics["built_cact"],
            module.pairwise_divergence(base, lora),
            divergence,
        )
        self.assertEqual(disposition, "INCONCLUSIVE")
        self.assertEqual(reasons, ["lora_not_load_bearing_on_canary"])

    def test_disposition_detects_bounded_deployment_divergence(self):
        expected = [case["expected"] for case in self.cases]
        built_predictions = list(expected)
        built_predictions[0] = "READY"
        built_predictions[1] = "UNKNOWN"
        base = self.rows("base_reference")
        lora = self.rows("lora_reference")
        built = self.rows("built_cact", built_predictions)
        divergence = module.pairwise_divergence(lora, built)
        disposition, reasons = module.decide(
            self.manifest,
            module.surface_metrics(base),
            module.surface_metrics(lora),
            module.surface_metrics(built),
            module.pairwise_divergence(base, lora),
            divergence,
        )
        self.assertEqual(disposition, "DEPLOYMENT_DIVERGENCE_REPRODUCED")
        self.assertIn("reference_built_pairwise_mismatch", reasons)

    def test_disposition_detects_applicability_regression_without_build_divergence(self):
        expected = [case["expected"] for case in self.cases]
        lora_predictions = list(expected)
        negative_indices = [
            i for i, case in enumerate(self.cases) if case["expected"] == "NO_CALL"
        ]
        lora_predictions[negative_indices[0]] = "PROBE"
        lora_predictions[negative_indices[1]] = "READY"

        base = self.rows("base_reference")
        lora = self.rows("lora_reference", lora_predictions)
        built = self.rows("built_cact", lora_predictions)
        divergence = module.pairwise_divergence(lora, built)
        disposition, reasons = module.decide(
            self.manifest,
            module.surface_metrics(base),
            module.surface_metrics(lora),
            module.surface_metrics(built),
            module.pairwise_divergence(base, lora),
            divergence,
        )
        self.assertEqual(disposition, "APPLICABILITY_REGRESSION_REPRODUCED")
        self.assertIn("lora_negative_no_call_drop", reasons)

    def test_invalid_prediction_is_inconclusive_not_divergence(self):
        expected = [case["expected"] for case in self.cases]
        changed = list(expected)
        changed[0] = "INVALID"
        lora = self.rows("lora_reference", changed)
        built = self.rows("built_cact", changed)
        disposition, reasons = module.decide(
            self.manifest,
            module.surface_metrics(self.rows("base_reference")),
            module.surface_metrics(lora),
            module.surface_metrics(built),
            module.pairwise_divergence(self.rows("base_reference"), lora),
            module.pairwise_divergence(lora, built),
        )
        self.assertEqual(disposition, "INCONCLUSIVE")
        self.assertEqual(reasons, ["invalid_prediction_observed"])

    def test_wheel_verification_binds_filename_and_sha256(self):
        expected = self.manifest["upstream_snapshot"]
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            d = pathlib.Path(tmp)
            wheel = d / expected["wheel_filename"]
            wheel.write_bytes(b"not-the-real-wheel")
            args = type("Args", (), {"manifest": MANIFEST, "wheel": wheel})()
            with self.assertRaisesRegex(SystemExit, "WHEEL_SHA256_MISMATCH"):
                module._verify_wheel(args)

            wrong_name = d / "other.whl"
            wrong_name.write_bytes(b"not-the-real-wheel")
            args = type("Args", (), {"manifest": MANIFEST, "wheel": wrong_name})()
            with self.assertRaisesRegex(SystemExit, "WHEEL_FILENAME_MISMATCH"):
                module._verify_wheel(args)

    def test_exact_file_identity_rejects_size_or_hash_drift(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = pathlib.Path(tmp) / "asset.bin"
            path.write_bytes(b"anchored-bytes")
            expected_sha = module.sha256_file(path)
            identity = module.verify_file_identity(
                path,
                expected_sha256=expected_sha,
                expected_size=len(b"anchored-bytes"),
                label="test asset",
            )
            self.assertEqual(identity["sha256"], expected_sha)

            with self.assertRaisesRegex(ValueError, "size mismatch"):
                module.verify_file_identity(
                    path,
                    expected_sha256=expected_sha,
                    expected_size=1,
                    label="test asset",
                )
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                module.verify_file_identity(
                    path,
                    expected_sha256="0" * 64,
                    expected_size=len(b"anchored-bytes"),
                    label="test asset",
                )

    def test_engine_resolution_uses_exact_runtime_path_and_fails_if_missing(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            engine = pathlib.Path(tmp) / "libneedle3.so"
            engine.write_bytes(b"engine")

            class FakeNeedle:
                @staticmethod
                def _library_path(generation):
                    self.assertEqual(generation, 3)
                    return str(engine)

            resolved = module.resolve_engine_path(FakeNeedle)
            self.assertEqual(resolved, engine.resolve())

            engine.unlink()
            with self.assertRaisesRegex(RuntimeError, "does not exist"):
                module.resolve_engine_path(FakeNeedle)

    def test_provenance_requires_one_exact_chain(self):
        for surface in module.SURFACES:
            module.validate_provenance(
                self.manifest,
                self.provenance(surface),
                surface,
            )

        wrong = self.provenance("built_cact")
        wrong["package_version"] = "3.0.3"
        with self.assertRaisesRegex(ValueError, "package_version"):
            module.validate_provenance(self.manifest, wrong, "built_cact")

    def test_aggregate_rejects_cross_surface_checkpoint_or_adapter_mismatch(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            d = pathlib.Path(tmp)
            result_paths = {}
            provenance_paths = {}
            for surface in module.SURFACES:
                result_path = d / f"{surface}.jsonl"
                module.write_jsonl(result_path, self.rows(surface))
                result_paths[surface] = result_path

                provenance = self.provenance(surface)
                if surface == "built_cact":
                    provenance["lora_adapter_sha256"] = "e" * 64
                provenance_path = d / f"{surface}.provenance.json"
                module.write_json(provenance_path, provenance)
                provenance_paths[surface] = provenance_path

            with self.assertRaisesRegex(ValueError, "LoRA adapter mismatch"):
                module.build_receipt(MANIFEST, result_paths, provenance_paths)

            built = module.load_json(provenance_paths["built_cact"])
            built["lora_adapter_sha256"] = "b" * 64
            built["base_checkpoint_sha256"] = "f" * 64
            module.write_json(provenance_paths["built_cact"], built)
            with self.assertRaisesRegex(ValueError, "frozen runtime asset"):
                module.build_receipt(MANIFEST, result_paths, provenance_paths)

    def test_full_receipt_binds_surface_results_and_provenance(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            d = pathlib.Path(tmp)
            result_paths = {}
            provenance_paths = {}
            for surface in module.SURFACES:
                result_path = d / f"{surface}.jsonl"
                module.write_jsonl(result_path, self.rows(surface))
                result_paths[surface] = result_path
                provenance_path = d / f"{surface}.provenance.json"
                module.write_json(provenance_path, self.provenance(surface))
                provenance_paths[surface] = provenance_path

            receipt = module.build_receipt(MANIFEST, result_paths, provenance_paths)
            self.assertEqual(receipt["disposition"], "INCONCLUSIVE")
            self.assertEqual(
                receipt["disposition_reasons"],
                ["lora_not_load_bearing_on_canary"],
            )
            self.assertEqual(receipt["fixture_sha256"], self.manifest["fixture"]["sha256"])
            self.assertEqual(
                receipt["surface_provenance"]["lora_reference"]["lora_adapter_sha256"],
                receipt["surface_provenance"]["built_cact"]["lora_adapter_sha256"],
            )
            for surface in module.SURFACES:
                self.assertEqual(receipt["metrics"][surface]["rows"], 12)

    def test_consumer_rebuild_rejects_tampered_receipt(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            d = pathlib.Path(tmp)
            result_paths = {}
            provenance_paths = {}
            for surface in module.SURFACES:
                result_path = d / f"{surface}.jsonl"
                module.write_jsonl(result_path, self.rows(surface))
                result_paths[surface] = result_path
                provenance_path = d / f"{surface}.provenance.json"
                module.write_json(provenance_path, self.provenance(surface))
                provenance_paths[surface] = provenance_path

            receipt = module.build_receipt(MANIFEST, result_paths, provenance_paths)
            receipt_path = d / "receipt.json"
            module.write_json(receipt_path, receipt)

            args = type(
                "Args",
                (),
                {
                    "receipt": receipt_path,
                    "manifest": MANIFEST,
                    "base_results": result_paths["base_reference"],
                    "lora_results": result_paths["lora_reference"],
                    "built_results": result_paths["built_cact"],
                    "base_provenance": provenance_paths["base_reference"],
                    "lora_provenance": provenance_paths["lora_reference"],
                    "built_provenance": provenance_paths["built_cact"],
                },
            )()
            self.assertEqual(module._validate_receipt(args), 0)

            changed = copy.deepcopy(receipt)
            changed["disposition"] = "NO_CURRENT_SIGNAL"
            module.write_json(receipt_path, changed)
            with self.assertRaisesRegex(SystemExit, "RECEIPT_MISMATCH"):
                module._validate_receipt(args)

    def test_missing_artifact_fault_consumes_promoted_taxonomy(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            d = pathlib.Path(tmp)
            checkpoint = {
                "schema_version": "needle-execution-checkpoint-v1",
                "identity": {
                    "experiment_sha": "a" * 40,
                    "launcher_sha": "b" * 40,
                    "run_id": "needle3-canary",
                    "run_attempt": 1,
                    "stage": "built_cact",
                    "unit": "canary",
                },
                "execution_status": "SUCCEEDED",
                "lifecycle_state": "EXECUTING",
                "artifact_scan_status": "COMPLETE",
                "command_exit_code": 0,
                "command_signal": None,
                "artifact_scan_errors": [],
                "artifacts": [],
            }
            cp = d / "checkpoint.json"
            module.write_json(cp, checkpoint)
            missing = d / "tuned.cact"
            receipt = module.build_missing_artifact_fault("built_cact", missing, cp)
            self.assertEqual(receipt["fault_class"], "ARTIFACT_MISSING")
            self.assertEqual(receipt["mapped_state"], "BLOCKED")
            self.assertEqual(
                receipt["required_next_evidence"],
                "verified_artifact_identity_or_reproduction",
            )
            self.assertEqual(receipt["classification_source"], "EXPLICIT_OBSERVATION")


if __name__ == "__main__":
    unittest.main()
