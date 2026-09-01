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
        self.assertIn("queue: max", text)
        self.assertNotIn("cancel-in-progress: true", text)
        test_index = text.index("python -m unittest discover -s tests -v")
        restore_index = text.index("python scripts/restore-needle-watch-state.py")
        collect_index = text.index("python scripts/collect-needle-watch.py")
        publish_index = text.index("python scripts/publish-needle-watch.py")
        self.assertLess(test_index, restore_index)
        self.assertLess(restore_index, collect_index)
        self.assertLess(collect_index, publish_index)
        self.assertEqual(text.count("contents: write"), 1)
        collect_text, publish_text = text.split("  publish:\n", 1)
        self.assertIn("  collect:\n", collect_text)
        self.assertIn("permissions:\n      contents: read", collect_text)
        self.assertNotIn("contents: write", collect_text)
        self.assertIn("    needs: collect", publish_text)
        self.assertIn("permissions:\n      contents: write", publish_text)
        self.assertIn("receipt_json: ${{ steps.handoff.outputs.receipt_json }}", collect_text)
        self.assertIn("receipt_sha256: ${{ steps.handoff.outputs.receipt_sha256 }}", collect_text)
        self.assertIn("python scripts/export-needle-watch-output.py", collect_text)
        self.assertIn("python scripts/import-needle-watch-output.py", publish_text)
        self.assertIn(
            "NEEDLE_WATCH_RECEIPT_JSON: ${{ needs.collect.outputs.receipt_json }}",
            publish_text,
        )
        self.assertIn(
            "NEEDLE_WATCH_RECEIPT_SHA256: ${{ needs.collect.outputs.receipt_sha256 }}",
            publish_text,
        )
        self.assertNotIn("upload-artifact", text)
        self.assertNotIn("download-artifact", text)
        self.assertIn("NEEDLE_WATCH_TARGET_REF: ${{ github.ref_name }}", text)
        self.assertNotIn("DATE_KEY=$(date -u +%F)", text)
        self.assertNotIn("data/${DATE_KEY}", text)
        self.assertNotIn("git add .", text)
        self.assertNotIn("git push\n", text)
        self.assertIn(
            "uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
            text,
        )
        self.assertIn(
            "uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0",
            text,
        )
        self.assertNotIn("uses: actions/checkout@v", text)
        self.assertNotIn("uses: actions/setup-python@v", text)
        self.assertIn('python-version: "3.12"', text)
        self.assertIn(
            'NEEDLE_WATCH_RUN_ID: ${{ github.run_id }}-attempt-${{ github.run_attempt }}',
            text,
        )


if __name__ == "__main__":
    unittest.main()
