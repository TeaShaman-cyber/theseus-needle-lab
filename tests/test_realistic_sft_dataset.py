import json
import pathlib
import unittest

from scripts.build_realistic_sft_dataset import build_semantic_cases, project_needle_case, build_outputs


ROOT = pathlib.Path(__file__).resolve().parents[1]
FAMILIES = ROOT / "experiments" / "needle-realistic-sft" / "source" / "families.json"


class RealisticSftSemanticDatasetContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.family_spec = json.loads(FAMILIES.read_text(encoding="utf-8"))
        cls.train, cls.heldout = build_semantic_cases(cls.family_spec)

    def test_exact_train_and_heldout_geometry(self):
        self.assertEqual(len(self.train), 360)
        self.assertEqual(len(self.heldout), 96)

        def counts(rows):
            out = {"PROBE": 0, "READY": 0, "UNKNOWN": 0, "NONE": 0}
            for row in rows:
                key = row["expected_decision"] or "NONE"
                out[key] += 1
            return out

        self.assertEqual(counts(self.train), {"PROBE": 100, "READY": 100, "UNKNOWN": 100, "NONE": 60})
        self.assertEqual(counts(self.heldout), {"PROBE": 24, "READY": 24, "UNKNOWN": 24, "NONE": 24})

    def test_case_ids_queries_and_family_splits_are_disjoint(self):
        all_rows = self.train + self.heldout
        case_ids = [row["case_id"] for row in all_rows]
        queries = [row["query"] for row in all_rows]
        self.assertEqual(len(case_ids), len(set(case_ids)))
        self.assertEqual(len(queries), len(set(queries)))

        train_families = {row["family_id"] for row in self.train}
        heldout_families = {row["family_id"] for row in self.heldout}
        self.assertTrue(train_families.isdisjoint(heldout_families))

    def test_every_record_is_repository_authored_and_contract_complete(self):
        required = {
            "case_id",
            "family_id",
            "split",
            "applicability",
            "expected_decision",
            "semantic_rule",
            "query",
            "rationale",
            "derivation_family",
            "entity_variant",
            "schema_contract",
            "source_kind",
        }
        for row in self.train + self.heldout:
            self.assertEqual(set(row), required)
            self.assertEqual(row["source_kind"], "synthetic_repo_authored")
            self.assertEqual(row["schema_contract"], "needle-route-uppercase-v1")
            if row["applicability"] == "route":
                self.assertIn(row["expected_decision"], {"PROBE", "READY", "UNKNOWN"})
            else:
                self.assertEqual(row["applicability"], "none")
                self.assertIsNone(row["expected_decision"])


if __name__ == "__main__":
    unittest.main()


class RealisticSftProjectionContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.family_spec = json.loads(FAMILIES.read_text(encoding="utf-8"))
        cls.train, cls.heldout = build_semantic_cases(cls.family_spec)
        cls.schema = {
            "name": "route",
            "parameters": {
                "type": "object",
                "properties": {"decision": {"type": "string", "enum": ["PROBE", "READY", "UNKNOWN"]}},
                "required": ["decision"],
            },
            "description": "Classify the current evidence state. Always use route for this classification. PROBE = current verification is needed and safely possible. READY = current authoritative evidence verifies the state. UNKNOWN = evidence is insufficient and no safe current probe is available.",
        }
        cls.prefix = "Use route to classify the following evidence:\n\n"

    def test_positive_and_negative_projection_are_exact_and_do_not_leak_audit_metadata(self):
        positive = next(row for row in self.train if row["expected_decision"] == "PROBE")
        negative = next(row for row in self.train if row["expected_decision"] is None)

        pos = project_needle_case(positive, self.schema, self.prefix)
        neg = project_needle_case(negative, self.schema, self.prefix)

        self.assertEqual(pos["query"], self.prefix + positive["query"])
        self.assertEqual(pos["tools"], [self.schema])
        self.assertEqual(pos["answers"], [{"name": "route", "arguments": {"decision": "PROBE"}}])
        self.assertEqual(neg["query"], negative["query"])
        self.assertEqual(neg["tools"], [self.schema])
        self.assertEqual(neg["answers"], [])
        for projected in (pos, neg):
            rendered = json.dumps(projected, ensure_ascii=False)
            self.assertNotIn("rationale", rendered)
            self.assertNotIn("semantic_rule", rendered)
            self.assertNotIn("reasoning", projected)
            self.assertNotIn("system", projected)

    def test_frozen_route_contract_bytes_match_accepted_stage_a_digests(self):
        import hashlib
        outputs = build_outputs(self.family_spec, self.schema, self.prefix)
        self.assertEqual(
            hashlib.sha256(outputs["files"]["contract/route-schema.json"]).hexdigest(),
            "e0892212cf97e9d728d8106f4c3fb35bbb09cf0a71bdd9a032b5f457a54ccb7a",
        )
        self.assertEqual(
            hashlib.sha256(outputs["files"]["contract/route-positive-prefix.txt"]).hexdigest(),
            "b8b1697130db2487e50125e2290cf623e3cc259a0647848b19bdf8c9fd465df7",
        )

    def test_build_outputs_are_byte_stable_and_manifests_bind_generated_files(self):
        first = build_outputs(self.family_spec, self.schema, self.prefix)
        second = build_outputs(self.family_spec, self.schema, self.prefix)
        self.assertEqual(first, second)

        for name in ["source/semantic-cases.jsonl", "data/train.needle.jsonl", "data/heldout.eval.jsonl"]:
            self.assertIn(name, first["files"])

        dataset_manifest = json.loads(first["files"]["manifests/dataset-manifest.json"].decode("utf-8"))
        heldout_manifest = json.loads(first["files"]["manifests/heldout-manifest.json"].decode("utf-8"))
        self.assertEqual(dataset_manifest["train_rows"], 360)
        self.assertEqual(heldout_manifest["heldout_rows"], 96)
        self.assertEqual(dataset_manifest["source_kind"], "synthetic_repo_authored")
        self.assertEqual(heldout_manifest["source_kind"], "synthetic_repo_authored")
        for manifest in (dataset_manifest, heldout_manifest):
            for binding in manifest["bindings"]:
                self.assertRegex(binding["sha256"], r"^[0-9a-f]{64}$")
                self.assertIn(binding["path"], first["files"])
