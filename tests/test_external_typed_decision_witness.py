import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_external_typed_decision_witness.py"
CONFIG = ROOT / "experiments/external-typed-decision-witness/anyjev-hbr1-v1.json"

SPEC = importlib.util.spec_from_file_location("external_witness", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


class ExternalTypedDecisionWitnessTests(unittest.TestCase):
    def make_source(self, root, *, s2_semantics="SAME"):
        root = pathlib.Path(root)
        storage_revision = "a" * 40
        experiment_revision = "b" * 40
        run_id = "77"

        manifest_path = root / "fixtures/manifest.json"
        manifest = {
            "schema": "theseus.anyjev-hbr1-manifest.v1",
            "outcome_escrow_in_candidate_input": False,
            "acceptance_authority": False,
            "permission_authority": False,
            "verification_authority": False,
            "promotion_authority": False,
            "surfaces": [
                {"surface_id": "S0_ORIGINAL", "expected_semantics": "SAME"},
                {"surface_id": "S2_FORMAT_PRESERVE", "expected_semantics": s2_semantics},
                {"surface_id": "S3_SEMANTIC_CHANGE_CONTROL", "expected_semantics": "CHANGED"},
            ],
        }
        write_json(manifest_path, manifest)
        manifest_sha = MOD.sha256_file(manifest_path)

        candidate_path = root / "receipts/candidate.json"
        candidate = {
            "schema": "theseus.anyjev-hbr1-candidate.v1",
            "repository_sha": experiment_revision,
            "run_id": run_id,
            "manifest": {"sha256": manifest_sha},
            "outcome_escrow_consumed": False,
            "calibration_claim": False,
            "jev_equivalence_claim": False,
            "acceptance_authority": False,
            "permission_authority": False,
            "verification_authority": False,
            "promotion_authority": False,
            "results": [
                {
                    "surface_id": "S0_ORIGINAL",
                    "requested_level": "L0",
                    "served_level": "L0",
                    "option_ids": ["A", "B"],
                    "probabilities": {"A": 0.5, "B": 0.5},
                },
                {
                    "surface_id": "S2_FORMAT_PRESERVE",
                    "requested_level": "L0",
                    "served_level": "L0",
                    "option_ids": ["A", "B"],
                    "probabilities": {"A": 0.7, "B": 0.3},
                },
                {
                    "surface_id": "S3_SEMANTIC_CHANGE_CONTROL",
                    "requested_level": "L0",
                    "served_level": "L0",
                    "option_ids": ["A", "B"],
                    "probabilities": {"A": 0.55, "B": 0.45},
                },
            ],
        }
        write_json(candidate_path, candidate)
        candidate_sha = MOD.sha256_file(candidate_path)

        comparison_path = root / "receipts/comparison.json"
        comparison = {
            "schema": "theseus.anyjev-hbr1-comparison.v1",
            "candidate_receipt_sha256": candidate_sha,
            "source_repository_sha": experiment_revision,
            "source_run_id": run_id,
            "surface_total_variation_from_S0": {
                "L0": {
                    "S2_FORMAT_PRESERVE": 0.2,
                    "S3_SEMANTIC_CHANGE_CONTROL": 0.05,
                }
            },
            "authority": {
                "acceptance": False,
                "outcome_is_label": False,
                "promotion": False,
                "verification": False,
            },
        }
        write_json(comparison_path, comparison)
        comparison_sha = MOD.sha256_file(comparison_path)

        config = {
            "schema": MOD.CONFIG_SCHEMA,
            "claim_scope": "BOUNDED_TYPED_DECISION_WITNESS_ONLY",
            "source": {
                "repository": "example/source",
                "storage_revision": storage_revision,
                "experiment_revision": experiment_revision,
                "run_id": run_id,
                "manifest": {
                    "path": "fixtures/manifest.json",
                    "sha256": manifest_sha,
                },
                "candidate_receipt": {
                    "path": "receipts/candidate.json",
                    "sha256": candidate_sha,
                },
                "comparison_receipt": {
                    "path": "receipts/comparison.json",
                    "sha256": comparison_sha,
                },
            },
            "metric": "TOTAL_VARIATION",
            "probability_surface": "L0",
            "comparisons": [
                {
                    "reference_surface": "S0_ORIGINAL",
                    "candidate_surface": "S2_FORMAT_PRESERVE",
                    "declared_semantic_relation": "SAME",
                },
                {
                    "reference_surface": "S0_ORIGINAL",
                    "candidate_surface": "S3_SEMANTIC_CHANGE_CONTROL",
                    "declared_semantic_relation": "CHANGED_CONTROL",
                },
            ],
            "mapped_state": "MODEL_OR_DOMAIN_WITNESS",
            "semantic_oracle": False,
            "scientific_acceptance_performed": False,
            "acceptance_authority": False,
            "permission_authority": False,
            "verification_authority": False,
            "promotion_authority": False,
        }
        return config, storage_revision

    def test_real_config_freezes_exact_hbr1_source(self):
        config = MOD.load_json(CONFIG)
        self.assertEqual(
            config["source"]["storage_revision"],
            "c8c0702597cbb395fe54e78354cca49e26b6bf01",
        )
        self.assertEqual(
            config["source"]["manifest"]["sha256"],
            "1eded12722cbd196f68b4cc551ac13052d7ec9ea0d9a72221a2e2d2e7b3d00e1",
        )
        self.assertEqual(
            config["source"]["candidate_receipt"]["sha256"],
            "81f8b726c6b6a32153e7bb3c98848aaf89c02d2958b0386f33621523d1df625e",
        )
        self.assertEqual(
            config["source"]["comparison_receipt"]["sha256"],
            "6a3b9e1ee721940f15d2649a44c8f21b49bf7c00e2f56d919514539e0e37bbf9",
        )

    def test_build_recomputes_two_separate_bounded_comparisons(self):
        with tempfile.TemporaryDirectory() as td:
            config, source_revision = self.make_source(td)
            receipt = MOD.build_witness(
                config,
                pathlib.Path(td),
                source_revision=source_revision,
                implementation_sha="c" * 40,
            )
        self.assertEqual(receipt["mapped_state"], "MODEL_OR_DOMAIN_WITNESS")
        self.assertTrue(receipt["model_or_domain_witness"])
        self.assertFalse(receipt["semantic_oracle"])
        self.assertFalse(receipt["scientific_acceptance_performed"])
        self.assertEqual(
            [row["declared_semantic_relation"] for row in receipt["comparisons"]],
            ["SAME", "CHANGED_CONTROL"],
        )
        self.assertAlmostEqual(receipt["comparisons"][0]["observed_value"], 0.2, places=15)
        self.assertAlmostEqual(receipt["comparisons"][1]["observed_value"], 0.05, places=15)

    def test_source_hash_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            config, source_revision = self.make_source(td)
            path = pathlib.Path(td) / config["source"]["candidate_receipt"]["path"]
            path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source hash mismatch"):
                MOD.build_witness(
                    config,
                    pathlib.Path(td),
                    source_revision=source_revision,
                    implementation_sha="c" * 40,
                )

    def test_manifest_relation_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            config, source_revision = self.make_source(td, s2_semantics="CHANGED")
            with self.assertRaisesRegex(ValueError, "SAME relation disagrees"):
                MOD.build_witness(
                    config,
                    pathlib.Path(td),
                    source_revision=source_revision,
                    implementation_sha="c" * 40,
                )

    def test_self_consistent_comparison_value_tamper_is_recomputed_and_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            config, source_revision = self.make_source(td)
            path = pathlib.Path(td) / config["source"]["comparison_receipt"]["path"]
            value = json.loads(path.read_text(encoding="utf-8"))
            value["surface_total_variation_from_S0"]["L0"]["S2_FORMAT_PRESERVE"] = 0.9
            write_json(path, value)
            config["source"]["comparison_receipt"]["sha256"] = MOD.sha256_file(path)
            with self.assertRaisesRegex(ValueError, "recomputed TV differs"):
                MOD.build_witness(
                    config,
                    pathlib.Path(td),
                    source_revision=source_revision,
                    implementation_sha="c" * 40,
                )

    def test_validate_rejects_witness_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            config, source_revision = self.make_source(td)
            receipt = MOD.build_witness(
                config,
                pathlib.Path(td),
                source_revision=source_revision,
                implementation_sha="c" * 40,
            )
            tampered = copy.deepcopy(receipt)
            tampered["comparisons"][0]["observed_value"] = 0.9
            with self.assertRaisesRegex(ValueError, "does not match exact recomputation"):
                MOD.validate_witness(
                    tampered,
                    config,
                    pathlib.Path(td),
                    source_revision=source_revision,
                    implementation_sha="c" * 40,
                )

    def test_wrong_storage_revision_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            config, _ = self.make_source(td)
            with self.assertRaisesRegex(ValueError, "storage revision mismatch"):
                MOD.build_witness(
                    config,
                    pathlib.Path(td),
                    source_revision="d" * 40,
                    implementation_sha="c" * 40,
                )


if __name__ == "__main__":
    unittest.main()
