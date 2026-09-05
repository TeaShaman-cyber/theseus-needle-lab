import unittest
from pathlib import Path


class ProjectCookbookContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.cookbook = cls.root / "docs" / "cookbook" / "README.md"

    def read_cookbook(self):
        self.assertTrue(self.cookbook.exists(), "docs/cookbook/README.md is missing")
        return self.cookbook.read_text(encoding="utf-8")

    def test_cookbook_discovery_marker_exists(self):
        self.assertTrue(self.cookbook.exists(), "docs/cookbook/README.md is missing")

    def test_initial_rules_are_bounded_and_evidence_backed(self):
        text = self.read_cookbook()
        for rule_id in ("NDL-001", "NDL-002", "NDL-003"):
            self.assertIn(rule_id, text)
        self.assertIn("Execution success is not scientific acceptance", text)
        self.assertIn("exact source revision", text)
        self.assertIn("SHA-256", text)
        self.assertIn("ACCEPTED", text)
        self.assertIn("REJECTED", text)
        self.assertIn("INCONCLUSIVE", text)

    def sections(self):
        text = self.read_cookbook()
        active = text.split("## Active rules", 1)[1].split("## Candidate lessons", 1)[0]
        candidate = text.split("## Candidate lessons", 1)[1].split("## Scope boundary", 1)[0]
        return active, candidate

    def test_sha256_requirement_is_artifact_scoped(self):
        active, _ = self.sections()
        self.assertIn("artifact", active.lower())
        self.assertIn("SHA-256", active)
        self.assertNotIn("artifacts and receipts must preserve", active.lower())

    def test_inconclusive_rule_does_not_import_stage_c_recovery_policy(self):
        active, _ = self.sections()
        for forbidden in (
            "infrastructure timeout",
            "unavailable verifier",
            "incomplete replica set",
            "missing readback",
            "recovery route",
        ):
            self.assertNotIn(forbidden, active.lower())

    def test_candidate_lessons_do_not_become_active_rules(self):
        active, candidate = self.sections()
        import re
        self.assertEqual(re.findall(r"NDL-\d{3}", active), ["NDL-001", "NDL-002", "NDL-003"])
        self.assertNotIn("Candidate lessons are not active guidance", active)
        self.assertIn("Candidate lessons are not active guidance", candidate)
        self.assertIn("reviewed repository change", candidate)


if __name__ == "__main__":
    unittest.main()
