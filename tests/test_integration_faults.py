import copy
import importlib.util
import json
import pathlib
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
            artifact_scan_status="IN_PROGRESS",
            command_exit_code=None,
        )
        observation = self.module.classify_checkpoint(ambiguous)
        self.assertEqual(observation["fault_class"], "EXECUTION_AMBIGUOUS")
        self.assertEqual(observation["evidence_status"], "PARTIAL")

        incomplete = checkpoint(
            execution_status="SUCCEEDED",
            artifact_scan_status="PARTIAL",
            command_exit_code=0,
        )
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
