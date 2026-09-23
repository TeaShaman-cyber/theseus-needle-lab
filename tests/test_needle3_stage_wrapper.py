import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "run_needle3_canary_stage.sh"


class Needle3StageWrapperTests(unittest.TestCase):
    def env(self):
        value = os.environ.copy()
        value.update(
            EXPERIMENT_SHA="a" * 40,
            LAUNCHER_SHA="b" * 40,
            GITHUB_RUN_ID="123",
            GITHUB_RUN_ATTEMPT="2",
        )
        return value

    def test_wrapper_binds_execution_and_diagnostic_receipts(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            work = pathlib.Path(tmp)
            (work / "scripts").symlink_to(ROOT / "scripts", target_is_directory=True)
            result = subprocess.run(
                [
                    "bash",
                    str(WRAPPER),
                    "tiny",
                    "--artifact-root",
                    "artifacts",
                    "--track",
                    "artifacts",
                    "--",
                    sys.executable,
                    "-c",
                    "import pathlib; pathlib.Path('artifacts').mkdir(); "
                    "pathlib.Path('artifacts/result.txt').write_text('ok')",
                ],
                cwd=work,
                env=self.env(),
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            checkpoint = json.loads(
                (work / "_evidence/telemetry/tiny/checkpoint.json").read_text()
            )
            summary = json.loads(
                (work / "_evidence/diagnostics/tiny.json").read_text()
            )
            self.assertEqual(checkpoint["identity"]["run_attempt"], 2)
            self.assertEqual(checkpoint["execution_status"], "SUCCEEDED")
            self.assertEqual(checkpoint["lifecycle_state"], "ARTIFACT_PROVENANCE")
            self.assertEqual(len(checkpoint["artifacts"]), 1)
            self.assertEqual(summary["stage"], "tiny")
            self.assertEqual(summary["exit_code"], 0)

    def test_wrapper_preserves_failed_command_exit(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            work = pathlib.Path(tmp)
            (work / "scripts").symlink_to(ROOT / "scripts", target_is_directory=True)
            result = subprocess.run(
                [
                    "bash",
                    str(WRAPPER),
                    "tiny_fail",
                    "--",
                    sys.executable,
                    "-c",
                    "import sys; sys.exit(19)",
                ],
                cwd=work,
                env=self.env(),
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 19)
            checkpoint = json.loads(
                (work / "_evidence/telemetry/tiny_fail/checkpoint.json").read_text()
            )
            summary = json.loads(
                (work / "_evidence/diagnostics/tiny_fail.json").read_text()
            )
            self.assertEqual(checkpoint["command_exit_code"], 19)
            self.assertEqual(summary["exit_code"], 19)


if __name__ == "__main__":
    unittest.main()
