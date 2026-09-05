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

    def test_candidate_lessons_do_not_become_active_rules(self):
        text = self.read_cookbook()
        self.assertIn("Candidate lessons are not active guidance", text)
        self.assertIn("reviewed repository change", text)


if __name__ == "__main__":
    unittest.main()
