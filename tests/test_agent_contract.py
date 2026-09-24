import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
README = ROOT / "README.md"

class AgentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = AGENTS.read_text(encoding="utf-8")
        cls.normalized = " ".join(cls.text.split())

    def test_contract_exists_and_is_discoverable(self):
        self.assertTrue(AGENTS.is_file())
        self.assertIn("[AGENTS.md](AGENTS.md)", README.read_text(encoding="utf-8"))

    def test_contract_points_to_canonical_methodology(self):
        for path in (
            "README.md",
            "docs/architecture.md",
            "docs/experiment-lifecycle.md",
            "docs/cookbook/README.md",
        ):
            self.assertIn(path, self.text)
        self.assertIn(
            "does not replace or outrank the canonical research documents",
            self.normalized,
        )

    def test_specified_prerequisites_are_explicit(self):
        for phrase in (
            "research question or hypothesis",
            "data / fixture / manifest identity",
            "configuration identity",
            "success criteria",
            "failure or falsifier criteria",
            "privacy classification",
        ):
            self.assertIn(phrase, self.normalized)

    def test_planned_prerequisites_are_explicit(self):
        for phrase in (
            "execution route",
            "expected artifacts and receipts",
            "deterministic QA route",
            "recovery / checkpoint boundary",
            "verification plan",
        ):
            self.assertIn(phrase, self.normalized)

    def test_evidence_boundaries_are_explicit(self):
        for phrase in (
            "QA does not prove",
            "A model/domain witness is bounded evidence",
            "Review findings are evidence, not authority",
            "Scientific acceptance is explicit",
            "Promotion is a consequential mutation separate from scientific acceptance",
            "authoritative readback",
        ):
            self.assertIn(phrase, self.normalized)

    def test_outcome_and_disposition_are_separate(self):
        self.assertIn("ACCEPTED | REJECTED | INCONCLUSIVE", self.text)
        self.assertIn(
            "PROMOTED | PARKED | SUPERSEDED | ABANDONED | BLOCKED",
            self.text,
        )

    def test_degraded_states_and_privacy_are_explicit(self):
        for state in ("DEGRADED", "BLOCKED", "UNKNOWN", "STALE", "REPROBE_REQUIRED"):
            self.assertIn(state, self.text)
        for phrase in (
            "secrets or credentials",
            "private corpora",
            "private conversation content",
        ):
            self.assertIn(phrase, self.text)

    def test_same_concern_conflict_fails_closed(self):
        self.assertIn("stop with BLOCKED", self.text)
        self.assertIn("Do not invent precedence", self.text)

    def test_benchmark_execution_requires_specified_and_planned(self):
        self.assertIn(
            "do not execute candidates until the benchmark Issue is both SPECIFIED and PLANNED",
            self.normalized,
        )
        self.assertIn("deterministic harness QA is not benchmark evidence", self.text)
        self.assertIn("runtime feasibility is not model-quality evidence", self.text)

if __name__ == "__main__":
    unittest.main()
