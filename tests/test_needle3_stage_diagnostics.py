import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "needle3_stage_diagnostics.py"


class Needle3StageDiagnosticsTests(unittest.TestCase):
    def run_stage(self, work, command):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--stage",
                "test_stage",
                "--summary",
                "diagnostics/summary.json",
                "--interval-seconds",
                "0.02",
                "--track",
                "tracked",
                "--",
                *command,
            ],
            cwd=work,
            text=True,
            capture_output=True,
        )

    def test_success_preserves_exit_code_and_writes_resource_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            result = self.run_stage(
                work,
                [
                    sys.executable,
                    "-c",
                    "import pathlib,time; pathlib.Path('tracked').mkdir(); "
                    "pathlib.Path('tracked/payload.bin').write_bytes(b'x'*4096); time.sleep(0.06)",
                ],
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("needle3_stage_heartbeat", result.stdout)
            self.assertIn("NEEDLE3_STAGE_SUMMARY=PASS", result.stdout)
            summary = json.loads((work / "diagnostics/summary.json").read_text())
            self.assertEqual(summary["schema_version"], "theseus.needle3.stage_diagnostics.v1")
            self.assertEqual(summary["stage"], "test_stage")
            self.assertEqual(summary["exit_code"], 0)
            self.assertGreaterEqual(summary["sample_count"], 2)
            self.assertGreaterEqual(summary["final"]["tracked_kib"]["tracked"], 4)
            self.assertGreaterEqual(summary["elapsed_seconds"], 0.05)
            self.assertGreaterEqual(summary["child_max_rss_kib"], 0)

    def test_failure_returns_original_exit_code_and_still_writes_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            result = self.run_stage(
                work,
                [sys.executable, "-c", "import sys; sys.exit(23)"],
            )
            self.assertEqual(result.returncode, 23)
            summary = json.loads((work / "diagnostics/summary.json").read_text())
            self.assertEqual(summary["exit_code"], 23)

    def test_invalid_interval_fails_before_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            marker = work / "should-not-exist"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--stage",
                    "test_stage",
                    "--summary",
                    "diagnostics/summary.json",
                    "--interval-seconds",
                    "0",
                    "--",
                    sys.executable,
                    "-c",
                    f"import pathlib; pathlib.Path({str(marker)!r}).write_text('ran')",
                ],
                cwd=work,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
