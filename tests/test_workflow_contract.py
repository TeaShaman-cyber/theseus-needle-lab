import unittest
from pathlib import Path


class WorkflowContractTests(unittest.TestCase):
    def test_workflow_is_bounded_and_tests_before_collecting(self):
        root = Path(__file__).resolve().parents[1]
        workflow = root / ".github" / "workflows" / "needle-watch.yml"
        self.assertTrue(workflow.exists(), "needle-watch workflow is missing")
        text = workflow.read_text(encoding="utf-8")
        self.assertIn('cron: "37 14 * * *"', text)
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("contents: write", text)
        test_index = text.index("python -m unittest discover -s tests -v")
        collect_index = text.index("python scripts/collect-needle-watch.py")
        self.assertLess(test_index, collect_index)
        self.assertIn('git add "data/${DATE_KEY}/needle-watch.json" data/latest/needle-watch.json', text)
        self.assertNotIn("git add .", text)
        self.assertIn('python-version: "3.12"', text)


if __name__ == "__main__":
    unittest.main()
