import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "needle3-deployment-canary.yml"


class Needle3DeploymentWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_is_manual_exact_sha_and_read_only(self):
        text = self.text
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("\n  push:", text)
        self.assertNotIn("schedule:", text)
        self.assertIn("permissions:\n  contents: read", text)
        self.assertIn("ref: ${{ inputs.experiment_sha }}", text)
        self.assertIn('actual="$(git rev-parse HEAD)"', text)
        self.assertIn('test "$actual" = "$EXPERIMENT_SHA"', text)
        self.assertIn("LAUNCHER_SHA: ${{ github.workflow_sha }}", text)
        self.assertIn("timeout-minutes: 90", text)

    def test_qa_gate_precedes_expensive_environment_setup(self):
        text = self.text
        qa = text.index("- name: Repository QA gate")
        install = text.index("- name: Install exact Needle release")
        download = text.index("- name: Download exact base checkpoint")
        self.assertLess(qa, install)
        self.assertLess(install, download)
        self.assertIn("run: tools/dev/check", text)

    def test_release_and_training_contract_are_pinned(self):
        text = self.text
        self.assertIn("cactus-needle==3.0.4", text)
        self.assertIn('python-version: "3.12.14"', text)
        self.assertIn("--require-hashes", text)
        self.assertIn("requirements.lock.txt", text)
        self.assertIn("verify-wheel", text)
        self.assertIn("cactus_needle-3.0.4-py3-none-any.whl", text)
        self.assertIn("--epochs 2", text)
        self.assertIn("--batch-size 8", text)
        self.assertIn("--lora-rank 8", text)
        self.assertIn("--lora-alpha 16", text)
        self.assertIn("--max-len 512", text)
        self.assertIn("--val-split 0", text)
        self.assertIn("--seed 0", text)
        self.assertNotIn('numpy jax jaxlib "flax>=0.10.2" optax safetensors sentencepiece', text)
        self.assertNotIn("NEEDLE_API_KEY", text)

    def test_heavy_stages_use_combined_execution_and_resource_telemetry(self):
        text = self.text
        for stage in (
            "setup",
            "download_checkpoint",
            "resolve_engine",
            "base_reference",
            "train",
            "lora_reference",
            "build",
            "built_cact",
            "provenance",
            "aggregate",
        ):
            self.assertIn(
                f"scripts/run_needle3_canary_stage.sh {stage}",
                text,
            )
        self.assertIn("JAX_PLATFORM_NAME: cpu", text)
        self.assertIn('XLA_PYTHON_CLIENT_PREALLOCATE: "false"', text)

    def test_failure_evidence_and_artifact_identity_are_attempt_scoped(self):
        text = self.text
        self.assertIn("if: ${{ always() }}", text)
        self.assertIn("missing-artifact-fault", text)
        self.assertIn("--surface built_cact", text)
        artifact_name = (
            "needle3-deployment-canary-${{ github.run_id }}-${{ github.run_attempt }}"
        )
        self.assertEqual(text.count(artifact_name), 2)
        self.assertIn("retention-days: 14", text)

    def test_consumer_reads_back_exact_uploaded_receipt(self):
        text = self.text
        self.assertIn("readback:", text)
        self.assertIn("needs: produce", text)
        self.assertIn(
            "if: ${{ always() && needs.produce.result == 'success' }}",
            text,
        )
        self.assertIn("actions/download-artifact@v4", text)
        self.assertIn("scripts/execution_telemetry.py validate", text)
        self.assertIn("NEEDLE3_STAGE_READBACK_PASS", text)
        self.assertIn("validate-receipt", text)
        self.assertIn("NEEDLE3_CANARY_READBACK_PASS", text)

    def test_three_surface_chain_is_explicit_and_engine_is_runtime_resolved(self):
        text = self.text
        self.assertIn("--surface base_reference", text)
        self.assertIn("--surface lora_reference", text)
        self.assertIn("--surface built_cact", text)
        self.assertIn("resolve-engine", text)
        self.assertIn("--engine-binary '$engine'", text)
        self.assertIn("--lora _outputs/canary_lora.safetensors", text)
        self.assertIn("--built-cact _outputs/tuned.cact", text)


if __name__ == "__main__":
    unittest.main()
