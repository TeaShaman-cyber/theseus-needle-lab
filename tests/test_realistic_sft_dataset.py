import json
import pathlib
import unittest

from scripts.build_realistic_sft_dataset import build_semantic_cases


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
