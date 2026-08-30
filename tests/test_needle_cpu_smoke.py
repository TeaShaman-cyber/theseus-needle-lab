import importlib.util
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "experiments" / "needle-cpu-smoke" / "data.jsonl"
WORKFLOW = ROOT / ".github" / "workflows" / "needle-cpu-smoke.yml"
RECEIPT = ROOT / "scripts" / "write_smoke_receipt.py"


class SmokeContractTest(unittest.TestCase):
    def test_dataset_is_twelve_balanced_route_examples(self):
        rows = [json.loads(line) for line in DATA.read_text().splitlines() if line.strip()]
        self.assertEqual(len(rows), 12)
        decisions = []
        for row in rows:
            self.assertEqual(set(row), {"query", "tools", "reasoning", "answers"})
            self.assertIsInstance(row["query"], str)
            self.assertTrue(row["query"].strip())
            self.assertEqual(len(row["tools"]), 1)
            self.assertEqual(row["tools"][0]["name"], "route")
            self.assertEqual(len(row["answers"]), 1)
            answer = row["answers"][0]
            self.assertEqual(answer["name"], "route")
            decisions.append(answer["arguments"]["decision"])
        self.assertEqual({d: decisions.count(d) for d in set(decisions)}, {
            "PROBE": 4, "READY": 4, "UNKNOWN": 4,
        })

    def test_workflow_is_bounded_read_only_and_secret_free(self):
        text = WORKFLOW.read_text()
        self.assertIn("experiment/needle-cpu-smoke", text)
        self.assertRegex(text, r"permissions:\s*\n\s+contents: read")
        self.assertIn("timeout-minutes: 45", text)
        self.assertNotIn("secrets.", text)
        self.assertNotIn("OPENROUTER_API_KEY", text)
        self.assertIn("NEEDLE_TELEMETRY: \"0\"", text)
        self.assertIn("DO_NOT_TRACK: \"1\"", text)
        self.assertIn("cactus-needle[train]==2.0.8", text)
        self.assertIn("--epochs 1", text)
        self.assertIn("--batch-size 2", text)
        self.assertIn("--lora-rank 4", text)
        self.assertIn("--max-len 128", text)
        pins = {
            "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",
            "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
            "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
        }
        for action, sha in pins.items():
            self.assertIn(f"uses: {action}@{sha}", text)
        self.assertNotRegex(text, r"uses:\s+[^\s]+@(v\d+|main|master)\b")

    def test_receipt_parser_extracts_gnu_time_metrics(self):
        spec = importlib.util.spec_from_file_location("write_smoke_receipt", RECEIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        sample = """Elapsed (wall clock) time (h:mm:ss or m:ss): 1:02.50\nMaximum resident set size (kbytes): 123456\n"""
        metrics = module.parse_gnu_time(sample)
        self.assertEqual(metrics["peak_rss_kb"], 123456)
        self.assertAlmostEqual(metrics["wall_seconds"], 62.5)


if __name__ == "__main__":
    unittest.main()
