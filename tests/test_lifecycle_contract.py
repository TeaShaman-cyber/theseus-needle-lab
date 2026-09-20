import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE = ROOT / "docs" / "experiment-lifecycle.md"
ARCHITECTURE = ROOT / "docs" / "architecture.md"
README = ROOT / "README.md"


class LifecycleContractTests(unittest.TestCase):
    def test_process_stages_are_explicit_and_ordered(self):
        text = LIFECYCLE.read_text(encoding="utf-8")
        stages = (
            "SPECIFIED",
            "PLANNED",
            "WORKING",
            "QA",
            "EXECUTING",
            "MODEL_OR_DOMAIN_WITNESS",
            "REVIEW",
            "ACCEPTANCE_GATE",
            "PROMOTION",
            "READBACK",
            "DISPOSITION",
        )
        positions = [text.index(stage) for stage in stages]
        self.assertEqual(positions, sorted(positions))

    def test_research_outcome_is_separate_from_delivery_disposition(self):
        text = LIFECYCLE.read_text(encoding="utf-8")
        self.assertIn("ACCEPTED | REJECTED | INCONCLUSIVE", text)
        self.assertIn("PROMOTED | PARKED | SUPERSEDED | ABANDONED | BLOCKED", text)
        self.assertIn("independent of branch/PR state", text)
        self.assertIn("Historical uses", text)

    def test_qa_witness_review_acceptance_and_promotion_are_not_collapsed(self):
        text = LIFECYCLE.read_text(encoding="utf-8")
        self.assertIn("QA does not prove model quality", text)
        self.assertIn("Execution in progress", text)
        self.assertIn("A witness is evidence, not acceptance", text)
        self.assertIn("reviewer comment cannot silently", text)
        self.assertIn("PROMOTION", text)
        self.assertIn("authoritative target", text)

    def test_terminal_exits_do_not_require_promotion(self):
        text = LIFECYCLE.read_text(encoding="utf-8")
        self.assertIn("Terminal exits without promotion", text)
        self.assertIn("SPECIFIED -- abandoned --> DISPOSITION", text)
        self.assertIn("PLANNED -- superseded --> DISPOSITION", text)
        self.assertIn("WORKING -- blocked --> DISPOSITION", text)
        self.assertIn("QA -- blocked --> DISPOSITION", text)
        self.assertIn("EXECUTING -- failed / blocked --> DISPOSITION", text)
        self.assertIn(
            "ACCEPTANCE_GATE -- declined / no promotion authority --> DISPOSITION",
            text,
        )
        self.assertIn(
            "ACCEPTANCE_GATE -- accepted + authorized --> PROMOTION -> READBACK -> DISPOSITION",
            text,
        )

    def test_degraded_external_states_fail_open_claims_not_checks(self):
        text = LIFECYCLE.read_text(encoding="utf-8")
        for state in ("DEGRADED", "BLOCKED", "UNKNOWN", "STALE", "REPROBE_REQUIRED"):
            self.assertIn(state, text)
        self.assertIn("must not be converted into PASS", text)

    def test_issue_project_action_receipt_and_review_are_not_authority(self):
        architecture = ARCHITECTURE.read_text(encoding="utf-8")
        self.assertIn("An Issue is a coordination/evidence container", architecture)
        self.assertIn("GitHub Projects, Wiki, and Pages", architecture)
        self.assertIn("Workflow success is not scientific acceptance", architecture)
        self.assertIn("Review records findings; it does not itself grant", architecture)
        self.assertIn("Promotion is a separate consequential mutation", architecture)

    def test_readme_exposes_the_mature_flow(self):
        text = README.read_text(encoding="utf-8")
        self.assertIn(
            "QA -> execution -> model/domain witness -> review -> acceptance gate -> promotion/readback or direct disposition",
            text,
        )
        self.assertIn("ACCEPTED | REJECTED | INCONCLUSIVE", text)


if __name__ == "__main__":
    unittest.main()
