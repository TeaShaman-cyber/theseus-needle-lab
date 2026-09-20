import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "tools" / "dev" / "check"
DOCS_WORKFLOW = ROOT / ".github" / "workflows" / "docs-check.yml"
WATCH_WORKFLOW = ROOT / ".github" / "workflows" / "needle-watch.yml"


class DevCheckContractTests(unittest.TestCase):
    def test_canonical_dev_check_exists_and_is_executable(self):
        self.assertTrue(CHECK.is_file(), "tools/dev/check is missing")
        self.assertTrue(os.access(CHECK, os.X_OK), "tools/dev/check is not executable")

    def test_dev_check_is_lightweight_and_has_stable_contract_markers(self):
        text = CHECK.read_text(encoding="utf-8")
        self.assertIn("DEV_CHECK_PASS", text)
        self.assertIn("QA_CONTRACT_DRIFT", text)
        self.assertIn("python3 -m unittest discover -s tests -v", text)
        self.assertIn("python3 -m compileall -q", text)
        self.assertIn("python3 -m json.tool", text)
        self.assertIn("python3 scripts/check_tracked_whitespace.py", text)
        self.assertIn("git diff --check", text)
        for forbidden in (
            "needle finetune",
            "needle build",
            "gh workflow run",
            "gh api",
            "curl ",
            "wget ",
            "pip install",
            "npm install",
            "npm ci",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_lightweight_workflows_use_canonical_dev_check(self):
        docs = DOCS_WORKFLOW.read_text(encoding="utf-8")
        watch = WATCH_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("tools/dev/check", docs)
        self.assertIn("tools/dev/check", watch)
        self.assertNotIn("python -m unittest discover -s tests -v", watch)


if __name__ == "__main__":
    unittest.main()
