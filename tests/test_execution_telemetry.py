import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "execution_telemetry.py"


class ExecutionTelemetryTests(unittest.TestCase):
    def run_helper(self, work: pathlib.Path, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "run",
                "--experiment-sha",
                "a" * 40,
                "--launcher-sha",
                "b" * 40,
                "--run-id",
                "123",
                "--run-attempt",
                "2",
                "--stage",
                "train",
                "--unit",
                "R1",
                "--heartbeat-seconds",
                "0.05",
                "--checkpoint",
                "telemetry/execution-checkpoint.json",
                "--heartbeat",
                "telemetry/heartbeat.jsonl",
                "--artifact-root",
                "artifacts",
                "--",
                *command,
            ],
            cwd=work,
            text=True,
            capture_output=True,
        )

    def test_success_checkpoint_binds_identity_heartbeat_and_artifact_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            code = (
                "import pathlib,time;"
                "pathlib.Path('artifacts').mkdir();"
                "pathlib.Path('artifacts/payload.bin').write_bytes(b'abc');"
                "time.sleep(0.08)"
            )
            result = self.run_helper(work, [sys.executable, "-c", code])
            self.assertEqual(result.returncode, 0, result.stderr)
            checkpoint = json.loads((work / "telemetry/execution-checkpoint.json").read_text())
            self.assertEqual(checkpoint["schema_version"], "needle-execution-checkpoint-v1")
            self.assertEqual(checkpoint["execution_status"], "SUCCEEDED")
            self.assertEqual(checkpoint["lifecycle_state"], "ARTIFACT_PROVENANCE")
            self.assertEqual(checkpoint["identity"]["experiment_sha"], "a" * 40)
            self.assertEqual(checkpoint["identity"]["launcher_sha"], "b" * 40)
            self.assertEqual(checkpoint["identity"]["run_attempt"], 2)
            self.assertEqual(checkpoint["artifacts"][0]["path"], "artifacts/payload.bin")
            self.assertEqual(
                checkpoint["artifacts"][0]["sha256"],
                hashlib.sha256(b"abc").hexdigest(),
            )

            heartbeats = [
                json.loads(line)
                for line in (work / "telemetry/heartbeat.jsonl").read_text().splitlines()
            ]
            self.assertGreaterEqual(len(heartbeats), 2)
            self.assertEqual(heartbeats[-1]["sequence"], checkpoint["heartbeat_sequence"])

            validated = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "validate",
                    "--checkpoint",
                    str(work / "telemetry/execution-checkpoint.json"),
                    "--heartbeat",
                    str(work / "telemetry/heartbeat.jsonl"),
                    "--root",
                    str(work),
                    "--expected-experiment-sha",
                    "a" * 40,
                    "--expected-launcher-sha",
                    "b" * 40,
                    "--expected-stage",
                    "train",
                    "--expected-unit",
                    "R1",
                    "--expected-execution-status",
                    "SUCCEEDED",
                    "--expected-lifecycle-state",
                    "ARTIFACT_PROVENANCE",
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertIn("EXECUTION_CHECKPOINT_VALID=PASS", validated.stdout)

    def test_failed_command_preserves_partial_artifact_and_original_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            code = (
                "import pathlib,sys;"
                "pathlib.Path('artifacts').mkdir();"
                "pathlib.Path('artifacts/recoverable.txt').write_text('saved');"
                "sys.exit(17)"
            )
            result = self.run_helper(work, [sys.executable, "-c", code])
            self.assertEqual(result.returncode, 17)
            checkpoint = json.loads((work / "telemetry/execution-checkpoint.json").read_text())
            self.assertEqual(checkpoint["execution_status"], "FAILED")
            self.assertEqual(checkpoint["command_exit_code"], 17)
            self.assertEqual(checkpoint["lifecycle_state"], "ARTIFACT_PROVENANCE")
            self.assertEqual(checkpoint["artifacts"][0]["path"], "artifacts/recoverable.txt")

    def test_invalid_identity_fails_closed_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "run",
                    "--experiment-sha",
                    "not-a-sha",
                    "--launcher-sha",
                    "b" * 40,
                    "--run-id",
                    "1",
                    "--run-attempt",
                    "1",
                    "--stage",
                    "train",
                    "--",
                    sys.executable,
                    "-c",
                    "raise SystemExit(0)",
                ],
                cwd=work,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("INVALID_EXPERIMENT_SHA", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
