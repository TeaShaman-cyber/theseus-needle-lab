import copy
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "integration_faults.py"
TAXONOMY = ROOT / "config" / "integration-fault-taxonomy.json"
CANARY_FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "integration-faults"
    / "needle3-canary-artifact-missing.json"
)
WORKFLOW = ROOT / ".github" / "workflows" / "execution-recovery-canary.yml"


def load_module():
    spec = importlib.util.spec_from_file_location("integration_faults", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def checkpoint(
    *,
    execution_status="FAILED",
    lifecycle_state="ARTIFACT_PROVENANCE",
    artifact_scan_status="COMPLETE",
    command_exit_code=17,
    command_signal=None,
):
    return {
        "schema_version": "needle-execution-checkpoint-v1",
        "identity": {
            "experiment_sha": "a" * 40,
            "launcher_sha": "b" * 40,
            "run_id": "123",
            "run_attempt": 2,
            "stage": "recovery_canary",
            "unit": "PR",
        },
        "execution_status": execution_status,
        "lifecycle_state": lifecycle_state,
        "artifact_scan_status": artifact_scan_status,
        "command_exit_code": command_exit_code,
        "command_signal": command_signal,
        "artifact_scan_errors": [],
        "artifacts": [
            {
                "path": "artifacts/recoverable.txt",
                "bytes": 9,
                "sha256": "c" * 64,
            }
        ],
    }


class IntegrationFaultContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        cls.taxonomy = cls.module.load_taxonomy(TAXONOMY)

    def test_taxonomy_has_bounded_states_and_no_success_aliases(self):
        expected = {
            "INVALID_IDENTITY": "BLOCKED",
            "EXECUTION_FAILED": "BLOCKED",
            "EXECUTION_INTERRUPTED": "BLOCKED",
            "EXECUTION_AMBIGUOUS": "UNKNOWN",
            "ARTIFACT_PROVENANCE_INCOMPLETE": "DEGRADED",
            "ARTIFACT_MISSING": "BLOCKED",
            "ARTIFACT_CORRUPT_OR_HASH_MISMATCH": "BLOCKED",
            "READBACK_UNAVAILABLE": "REPROBE_REQUIRED",
            "READBACK_MISMATCH": "REPROBE_REQUIRED",
            "REFERENCE_BUILD_SEMANTIC_MISMATCH": "MODEL_OR_DOMAIN_WITNESS",
            "QUANTIZATION_EXPORT_DIVERGENCE": "MODEL_OR_DOMAIN_WITNESS",
            "HELPER_VERIFIER_EXACTNESS_LOSS": "MODEL_OR_DOMAIN_WITNESS",
            "ACCEPTANCE_OR_CALL_RATE_COLLAPSE": "MODEL_OR_DOMAIN_WITNESS",
            "PERFORMANCE_INVERSION": "MODEL_OR_DOMAIN_WITNESS",
        }
        classes = self.taxonomy["classes"]
        self.assertEqual(
            {name: spec["mapped_state"] for name, spec in classes.items()},
            expected,
        )
        serialized = json.dumps(self.taxonomy, sort_keys=True)
        self.assertNotIn('"PASS"', serialized)
        self.assertNotIn('"NO_CALL"', serialized)
        self.assertNotIn('"REJECTED"', serialized)
        self.assertNotIn('"ACCEPTED"', serialized)

    def test_taxonomy_cannot_expand_lifecycle_states_or_classification_sources(self):
        changed = copy.deepcopy(self.taxonomy)
        changed["allowed_mapped_states"].append("FOO")
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "taxonomy.json"
            path.write_text(
                json.dumps(changed, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "lifecycle contract"):
                self.module.load_taxonomy(path)

        self.assertEqual(
            self.taxonomy["classes"]["EXECUTION_FAILED"]["allowed_classification_sources"],
            ["CHECKPOINT_DERIVED"],
        )
        observation = {
            "fault_class": "EXECUTION_FAILED",
            "evidence_status": "VERIFIED",
            "classification_source": "EXPLICIT_OBSERVATION",
            "observed_surface": "recovery_canary",
            "metric_or_check": "command_exit_code",
            "observed_value": 17,
            "expected_or_reference_value": 0,
        }
        with self.assertRaisesRegex(ValueError, "classification source"):
            self.module.build_receipt(
                observation,
                checkpoint(),
                checkpoint_sha256="d" * 64,
                taxonomy=self.taxonomy,
            )

    def test_each_fault_names_missing_or_next_evidence_without_deciding_authority(self):
        for name, spec in self.taxonomy["classes"].items():
            with self.subTest(name=name):
                self.assertIsInstance(spec["required_next_evidence"], str)
                self.assertTrue(spec["required_next_evidence"])
                self.assertNotIn(
                    spec["required_next_evidence"],
                    {"PROMOTE", "MERGE", "ACCEPT", "REJECT"},
                )

        cp = checkpoint(
            execution_status="RUNNING",
            lifecycle_state="EXECUTING",
            artifact_scan_status="NOT_STARTED",
            command_exit_code=None,
        )
        cp["artifacts"] = []
        observation = self.module.classify_checkpoint(cp)
        receipt = self.module.build_receipt(
            observation,
            cp,
            checkpoint_sha256="d" * 64,
            taxonomy=self.taxonomy,
        )
        self.assertEqual(receipt["mapped_state"], "UNKNOWN")
        self.assertEqual(
            receipt["required_next_evidence"],
            "terminal_execution_checkpoint",
        )

        tampered = copy.deepcopy(receipt)
        tampered["required_next_evidence"] = "PROMOTE"
        with self.assertRaisesRegex(ValueError, "required next evidence mismatch"):
            self.module.validate_receipt(tampered, self.taxonomy)

    def test_checkpoint_failure_classification_is_mechanical_only(self):
        observation = self.module.classify_checkpoint(checkpoint())
        self.assertEqual(observation["fault_class"], "EXECUTION_FAILED")
        self.assertEqual(observation["evidence_status"], "VERIFIED")

        signaled = checkpoint(command_exit_code=143, command_signal=15)
        observation = self.module.classify_checkpoint(signaled)
        self.assertEqual(observation["fault_class"], "EXECUTION_INTERRUPTED")
        self.assertEqual(observation["evidence_status"], "VERIFIED")

        ambiguous = checkpoint(
            execution_status="RUNNING",
            lifecycle_state="EXECUTING",
            artifact_scan_status="NOT_STARTED",
            command_exit_code=None,
        )
        ambiguous["artifacts"] = []
        observation = self.module.classify_checkpoint(ambiguous)
        self.assertEqual(observation["fault_class"], "EXECUTION_AMBIGUOUS")
        self.assertEqual(observation["evidence_status"], "PARTIAL")

        incomplete = checkpoint(
            execution_status="SUCCEEDED",
            artifact_scan_status="PARTIAL",
            command_exit_code=0,
        )
        incomplete["artifact_scan_errors"] = [
            {"path": "artifacts/recoverable.txt", "error_type": "CONCURRENT_MODIFICATION"}
        ]
        observation = self.module.classify_checkpoint(incomplete)
        self.assertEqual(
            observation["fault_class"],
            "ARTIFACT_PROVENANCE_INCOMPLETE",
        )
        self.assertEqual(observation["evidence_status"], "PARTIAL")

        healthy = checkpoint(
            execution_status="SUCCEEDED",
            artifact_scan_status="COMPLETE",
            command_exit_code=0,
        )
        self.assertIsNone(self.module.classify_checkpoint(healthy))

    def test_checkpoint_projection_rejects_internally_inconsistent_state(self):
        cases = []

        value = checkpoint(execution_status="SUCCEEDED", command_exit_code=17)
        cases.append(value)

        value = checkpoint(execution_status="FAILED", command_exit_code=0)
        cases.append(value)

        value = checkpoint(
            execution_status="FAILED",
            command_exit_code=143,
            command_signal=9,
        )
        cases.append(value)

        value = checkpoint(
            execution_status="RUNNING",
            lifecycle_state="EXECUTING",
            artifact_scan_status="IN_PROGRESS",
            command_exit_code=None,
        )
        cases.append(value)

        value = checkpoint(
            execution_status="SUCCEEDED",
            artifact_scan_status="COMPLETE",
            command_exit_code=0,
        )
        value["artifact_scan_errors"] = [{"path": "x", "error_type": "E"}]
        cases.append(value)

        value = checkpoint(
            execution_status="SUCCEEDED",
            artifact_scan_status="PARTIAL",
            command_exit_code=0,
        )
        value["artifact_scan_errors"] = []
        cases.append(value)

        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.module.classify_checkpoint(value)

    def test_checkpoint_derived_receipt_cannot_be_reclassified(self):
        cp = checkpoint()
        observation = self.module.classify_checkpoint(cp)
        receipt = self.module.build_receipt(
            observation,
            cp,
            checkpoint_sha256="d" * 64,
            taxonomy=self.taxonomy,
        )

        tampered = copy.deepcopy(receipt)
        tampered["fault_class"] = "EXECUTION_INTERRUPTED"
        tampered["metric_or_check"] = "command_signal"
        tampered["observed_value"] = 15
        tampered["expected_or_reference_value"] = 0

        self.module.validate_receipt(tampered, self.taxonomy)
        with self.assertRaisesRegex(ValueError, "checkpoint-derived classification mismatch"):
            self.module.validate_receipt_against_checkpoint(
                tampered,
                cp,
                "d" * 64,
                self.taxonomy,
            )

        bad_observation = copy.deepcopy(observation)
        bad_observation["fault_class"] = "EXECUTION_INTERRUPTED"
        bad_observation["metric_or_check"] = "command_signal"
        bad_observation["observed_value"] = 15
        with self.assertRaisesRegex(ValueError, "checkpoint-derived classification mismatch"):
            self.module.build_receipt(
                bad_observation,
                cp,
                checkpoint_sha256="d" * 64,
                taxonomy=self.taxonomy,
            )

    def test_partial_artifact_missing_and_ungrounded_invalid_identity_fail_closed(self):
        partial_missing = {
            "fault_class": "ARTIFACT_MISSING",
            "evidence_status": "PARTIAL",
            "observed_surface": "built_cact",
            "metric_or_check": "artifact_presence",
            "observed_value": False,
            "expected_or_reference_value": True,
        }
        with self.assertRaises(ValueError):
            self.module.build_receipt(
                partial_missing,
                checkpoint(),
                checkpoint_sha256="d" * 64,
                taxonomy=self.taxonomy,
            )

        weak_identity = {
            "fault_class": "INVALID_IDENTITY",
            "evidence_status": "VERIFIED",
            "observed_surface": "built_cact",
        }
        with self.assertRaisesRegex(ValueError, "missing required observation field"):
            self.module.build_receipt(
                weak_identity,
                taxonomy=self.taxonomy,
            )

    def test_cli_bound_validation_requires_checkpoint(self):
        observation = self.module.classify_checkpoint(checkpoint())
        receipt = self.module.build_receipt(
            observation,
            checkpoint(),
            checkpoint_sha256="d" * 64,
            taxonomy=self.taxonomy,
        )
        with tempfile.TemporaryDirectory() as tmp:
            receipt_path = pathlib.Path(tmp) / "receipt.json"
            receipt_path.write_text(
                json.dumps(receipt, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--taxonomy",
                    str(TAXONOMY),
                    "validate-receipt",
                    "--receipt",
                    str(receipt_path),
                ],
                text=True,
                capture_output=True,
            )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(
            "CHECKPOINT_REQUIRED_FOR_BOUND_VALIDATION",
            proc.stdout + proc.stderr,
        )

    def test_semantic_witness_requires_observed_comparison_and_never_decides_outcome(self):
        observation = {
            "fault_class": "REFERENCE_BUILD_SEMANTIC_MISMATCH",
            "evidence_status": "VERIFIED",
            "observed_surface": "built_cact",
            "reference_surface": "lora_reference",
            "candidate_surface": "built_cact",
            "metric_or_check": "decision_equivalence",
            "observed_value": 0.73,
            "expected_or_reference_value": 1.0,
            "notes": "bounded synthetic witness",
        }
        receipt = self.module.build_receipt(
            observation,
            checkpoint(),
            checkpoint_sha256="d" * 64,
        )
        self.assertEqual(receipt["mapped_state"], "MODEL_OR_DOMAIN_WITNESS")
        self.assertEqual(receipt["classification_source"], "EXPLICIT_OBSERVATION")
        self.assertNotIn("scientific_outcome", receipt)
        self.module.validate_receipt(receipt, self.taxonomy)

        missing = copy.deepcopy(observation)
        missing.pop("reference_surface")
        with self.assertRaises(ValueError):
            self.module.build_receipt(
                missing,
                checkpoint(),
                checkpoint_sha256="d" * 64,
            )

    def test_unavailable_witness_evidence_cannot_be_promoted_to_verified_signal(self):
        observation = {
            "fault_class": "PERFORMANCE_INVERSION",
            "evidence_status": "UNAVAILABLE",
            "observed_surface": "built_cact",
            "reference_surface": "no_helper",
            "candidate_surface": "helper",
            "metric_or_check": "latency_seconds",
        }
        with self.assertRaises(ValueError):
            self.module.build_receipt(
                observation,
                checkpoint(),
                checkpoint_sha256="d" * 64,
            )

    def test_needle3_canary_missing_artifact_stays_blocked_not_no_current_signal(self):
        observation = json.loads(CANARY_FIXTURE.read_text(encoding="utf-8"))
        receipt = self.module.build_receipt(
            observation,
            checkpoint(),
            checkpoint_sha256="d" * 64,
        )
        self.assertEqual(receipt["fault_class"], "ARTIFACT_MISSING")
        self.assertEqual(receipt["mapped_state"], "BLOCKED")
        self.assertEqual(observation["canary_disposition"], "BLOCKED")
        self.assertNotEqual(observation["canary_disposition"], "NO_CURRENT_SIGNAL")
        self.module.validate_receipt(receipt, self.taxonomy)

    def test_receipt_binds_exact_taxonomy_digest_not_version_only(self):
        observation = self.module.classify_checkpoint(checkpoint())
        receipt = self.module.build_receipt(
            observation,
            checkpoint(),
            checkpoint_sha256="d" * 64,
            taxonomy=self.taxonomy,
        )
        self.assertRegex(receipt["taxonomy_sha256"], r"^[0-9a-f]{64}$")

        changed_taxonomy = copy.deepcopy(self.taxonomy)
        changed_taxonomy["classes"]["READBACK_UNAVAILABLE"]["allowed_evidence_status"] = [
            "PARTIAL"
        ]
        with self.assertRaisesRegex(ValueError, "taxonomy digest mismatch"):
            self.module.validate_receipt(receipt, changed_taxonomy)

    def test_partial_artifact_provenance_preserves_scan_errors(self):
        partial = checkpoint(
            execution_status="SUCCEEDED",
            artifact_scan_status="PARTIAL",
            command_exit_code=0,
        )
        partial["artifact_scan_errors"] = [
            {
                "path": "artifacts/changing.bin",
                "error_type": "CONCURRENT_MODIFICATION",
            }
        ]
        observation = self.module.classify_checkpoint(partial)
        receipt = self.module.build_receipt(
            observation,
            partial,
            checkpoint_sha256="d" * 64,
            taxonomy=self.taxonomy,
        )
        self.assertEqual(
            receipt["execution"]["artifact_scan_errors"],
            partial["artifact_scan_errors"],
        )
        self.module.validate_receipt_against_checkpoint(
            receipt,
            partial,
            "d" * 64,
            self.taxonomy,
        )

    def test_receipt_validation_rejects_mapping_tamper(self):
        observation = self.module.classify_checkpoint(checkpoint())
        receipt = self.module.build_receipt(
            observation,
            checkpoint(),
            checkpoint_sha256="d" * 64,
        )
        tampered = copy.deepcopy(receipt)
        tampered["mapped_state"] = "MODEL_OR_DOMAIN_WITNESS"
        with self.assertRaises(ValueError):
            self.module.validate_receipt(tampered, self.taxonomy)

    def test_failure_canary_uploads_and_reads_back_fault_receipt(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("scripts/integration_faults.py classify-checkpoint", text)
        self.assertIn("receipts/integration-fault.json", text)
        self.assertIn("scripts/integration_faults.py validate-receipt", text)
        self.assertIn("INTEGRATION_FAULT_READBACK_PASS", text)


if __name__ == "__main__":
    unittest.main()
