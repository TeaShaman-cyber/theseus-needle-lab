import copy
import json
import unittest
from pathlib import Path

from scripts import validate_typed_decision_contract as contract


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts" / "typed-decision" / "v1.schema.json"
MAPPING = ROOT / "contracts" / "typed-decision" / "legacy-mapping.v1.json"
FIXTURES = ROOT / "contracts" / "typed-decision" / "fixtures.v1.jsonl"
DOC = ROOT / "docs" / "typed-decision-contract-v1.md"


class TypedDecisionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        cls.mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        cls.fixtures = contract.load_fixtures(FIXTURES)

    def test_schema_versions_core_vocabulary(self):
        self.assertEqual(
            self.schema["properties"]["schema"]["const"],
            "theseus.typed-decision.v1",
        )
        self.assertEqual(
            set(self.schema["properties"]["task"]["enum"]),
            {"EVIDENCE_ROUTING", "DRIFT_SENTINEL"},
        )
        self.assertEqual(
            set(self.schema["properties"]["outcome"]["enum"]),
            {"DECISION", "NO_CALL", "SIGNAL", "NO_SIGNAL", "ERROR"},
        )
        self.assertEqual(
            set(self.schema["properties"]["decision"]["enum"]),
            {"PROBE", "READY", "UNKNOWN", None},
        )

    def test_json_schema_encodes_semantic_branches(self):
        self.assertEqual(len(self.schema["oneOf"]), 7)
        self.assertEqual(
            {
                branch["title"]
                for branch in self.schema["oneOf"]
            },
            {
                "routing probe",
                "routing ready",
                "routing unknown",
                "routing no call",
                "drift signal",
                "drift no signal",
                "error envelope",
            },
        )
        confidence = self.schema["properties"]["advisory_confidence"]
        self.assertEqual(len(confidence["oneOf"]), 3)

    def test_schema_rejects_empty_probe_route_target_contractually(self):
        route_target = self.schema["properties"]["probe"]["oneOf"][1][
            "properties"
        ]["route_target"]
        self.assertEqual(route_target["minLength"], 1)

        value = copy.deepcopy(
            next(
                row["expected"]
                for row in self.fixtures
                if row["expected"]["decision"] == "PROBE"
            )
        )
        value["probe"]["route_target"] = ""
        with self.assertRaisesRegex(ValueError, "route_target"):
            contract.validate_envelope(value)

    def test_decision_cannot_use_drift_task(self):
        value = copy.deepcopy(self.fixtures[0]["expected"])
        value["task"] = "DRIFT_SENTINEL"
        with self.assertRaisesRegex(ValueError, "reserved for evidence routing"):
            contract.validate_envelope(value)

    def test_all_fixtures_validate(self):
        for row in self.fixtures:
            with self.subTest(case_id=row["case_id"]):
                contract.validate_envelope(row["expected"])

    def test_fixture_coverage_matches_issue_55(self):
        families = {row["family"] for row in self.fixtures}
        for required in {
            "current",
            "stale",
            "conflicting",
            "insufficient",
            "negative_control",
            "drift_signal",
            "error",
        }:
            self.assertIn(required, families)

        outcomes = {row["expected"]["outcome"] for row in self.fixtures}
        self.assertEqual(
            outcomes,
            {"DECISION", "NO_CALL", "SIGNAL", "NO_SIGNAL", "ERROR"},
        )

    def test_no_call_unknown_and_error_remain_distinct(self):
        by_id = {row["case_id"]: row["expected"] for row in self.fixtures}
        self.assertEqual(
            by_id["negative-control-off-topic"]["outcome"],
            "NO_CALL",
        )
        self.assertEqual(
            by_id["insufficient-no-current-source"]["decision"],
            "UNKNOWN",
        )
        self.assertEqual(
            by_id["invalid-model-output"]["outcome"],
            "ERROR",
        )

    def test_issue_26_legacy_mapping_preserves_labels(self):
        mapping = self.mapping["mappings"]["needle_issue_26_routing"]
        self.assertEqual(mapping["status"], "MACHINE_OUTPUT_MAPPED")
        labels = mapping["historical_labels"]
        for value in ("PROBE", "READY", "UNKNOWN"):
            self.assertEqual(
                labels[value],
                {"outcome": "DECISION", "decision": value},
            )
        self.assertEqual(
            labels["NO_CALL"],
            {"outcome": "NO_CALL", "decision": None},
        )
        self.assertEqual(labels["INVALID"]["outcome"], "ERROR")
        self.assertEqual(
            labels["INVALID"]["error_code"],
            "INVALID_MODEL_OUTPUT",
        )

    def test_historical_tuned_confidence_none_is_unavailable(self):
        confidence = self.mapping["mappings"]["needle_issue_26_routing"][
            "confidence"
        ]
        self.assertEqual(
            confidence["tuned_confidence_none"],
            {"kind": "UNAVAILABLE", "value": None, "calibrated": False},
        )
        self.assertFalse(confidence["scoring_or_authority_use"])

    def test_issue_5_mapping_does_not_invent_machine_history(self):
        mapping = self.mapping["mappings"]["needle_issue_5_drift_sentinel"]
        self.assertEqual(
            mapping["status"],
            "SEMANTIC_ONLY_NO_VERSIONED_MACHINE_OUTPUT",
        )
        self.assertEqual(
            mapping["historical_meaning"]["drift_signal_proposal"]["outcome"],
            "SIGNAL",
        )
        self.assertEqual(
            mapping["historical_meaning"]["no_drift_or_abstain"]["outcome"],
            "NO_SIGNAL",
        )
        self.assertFalse(
            mapping["historical_meaning"]["auto_mutation_authorized"]
        )

    def test_authority_grant_cannot_be_smuggled_into_core_envelope(self):
        value = copy.deepcopy(self.fixtures[0]["expected"])
        value["authority_granted"] = True
        with self.assertRaisesRegex(ValueError, "keys"):
            contract.validate_envelope(value)

    def test_document_states_authority_boundary(self):
        text = DOC.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        self.assertIn("does not promote runtime state to VERIFIED", normalized)
        self.assertIn("UNKNOWN is not NO_CALL", normalized)
        self.assertIn("confidence=None", normalized)
        self.assertIn(
            "Mutation and consequential promotion remain outside",
            normalized,
        )


if __name__ == "__main__":
    unittest.main()
