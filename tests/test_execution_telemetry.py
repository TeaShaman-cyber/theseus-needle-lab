import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "execution_telemetry.py"


spec = importlib.util.spec_from_file_location("execution_telemetry", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


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
            self.assertEqual(checkpoint["artifact_scan_status"], "COMPLETE")
            self.assertEqual(checkpoint["artifact_scan_errors"], [])
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
            self.assertGreaterEqual(len(heartbeats), 3)
            self.assertEqual(heartbeats[-1]["sequence"], checkpoint["heartbeat_sequence"])
            self.assertEqual(heartbeats[-1]["execution_status"], checkpoint["execution_status"])
            self.assertEqual(heartbeats[-1]["lifecycle_state"], checkpoint["lifecycle_state"])
            self.assertEqual(heartbeats[-1]["artifact_scan_status"], checkpoint["artifact_scan_status"])

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
            self.assertEqual(checkpoint["artifact_scan_status"], "COMPLETE")
            self.assertEqual(checkpoint["artifact_scan_errors"], [])
            self.assertEqual(checkpoint["lifecycle_state"], "ARTIFACT_PROVENANCE")
            self.assertEqual(checkpoint["artifacts"][0]["path"], "artifacts/recoverable.txt")

    def test_signal_termination_uses_shell_standard_exit_code_and_records_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            code = (
                "import os,pathlib,signal;"
                "pathlib.Path('artifacts').mkdir();"
                "pathlib.Path('artifacts/recoverable.txt').write_text('saved');"
                "os.kill(os.getpid(), signal.SIGTERM)"
            )
            result = self.run_helper(work, [sys.executable, "-c", code])
            self.assertEqual(result.returncode, 128 + 15)
            checkpoint = json.loads((work / "telemetry/execution-checkpoint.json").read_text())
            self.assertEqual(checkpoint["execution_status"], "FAILED")
            self.assertEqual(checkpoint["command_signal"], 15)
            self.assertEqual(checkpoint["command_exit_code"], 143)
            self.assertEqual(checkpoint["lifecycle_state"], "ARTIFACT_PROVENANCE")
            self.assertEqual(checkpoint["artifacts"][0]["path"], "artifacts/recoverable.txt")

    def test_hidden_files_are_excluded_to_match_default_artifact_uploads(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            code = (
                "import pathlib;"
                "pathlib.Path('artifacts').mkdir();"
                "pathlib.Path('artifacts/visible.txt').write_text('visible');"
                "pathlib.Path('artifacts/.hidden.txt').write_text('hidden')"
            )
            result = self.run_helper(work, [sys.executable, "-c", code])
            self.assertEqual(result.returncode, 0, result.stderr)
            checkpoint = json.loads((work / "telemetry/execution-checkpoint.json").read_text())
            self.assertEqual(
                [artifact["path"] for artifact in checkpoint["artifacts"]],
                ["artifacts/visible.txt"],
            )

    def test_hidden_artifact_root_is_excluded_to_match_default_uploads(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            code = (
                "import pathlib;"
                "pathlib.Path('.artifacts').mkdir();"
                "pathlib.Path('.artifacts/result.json').write_text('{}')"
            )
            result = subprocess.run(
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
                    "1",
                    "--stage",
                    "train",
                    "--checkpoint",
                    "telemetry/execution-checkpoint.json",
                    "--heartbeat",
                    "telemetry/heartbeat.jsonl",
                    "--artifact-root",
                    ".artifacts",
                    "--",
                    sys.executable,
                    "-c",
                    code,
                ],
                cwd=work,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            checkpoint = json.loads((work / "telemetry/execution-checkpoint.json").read_text())
            self.assertEqual(checkpoint["artifact_scan_status"], "COMPLETE")
            self.assertEqual(checkpoint["artifacts"], [])

    def test_external_symlink_is_skipped_without_masking_command_status(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside_tmp:
            work = pathlib.Path(tmp)
            outside = pathlib.Path(outside_tmp) / "outside.txt"
            outside.write_text("outside")
            code = (
                "import os,pathlib,sys;"
                "pathlib.Path('artifacts').mkdir();"
                "pathlib.Path('artifacts/visible.txt').write_text('visible');"
                f"os.symlink({str(outside)!r}, 'artifacts/outside-link');"
                "sys.exit(17)"
            )
            result = self.run_helper(work, [sys.executable, "-c", code])
            self.assertEqual(result.returncode, 17)
            checkpoint = json.loads((work / "telemetry/execution-checkpoint.json").read_text())
            self.assertEqual(checkpoint["execution_status"], "FAILED")
            self.assertEqual(checkpoint["command_exit_code"], 17)
            self.assertEqual(
                [artifact["path"] for artifact in checkpoint["artifacts"]],
                ["artifacts/visible.txt"],
            )

    def test_per_artifact_scan_error_is_recorded_without_losing_other_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            root = work / "artifacts"
            root.mkdir()
            good = root / "good.txt"
            bad = root / "bad.txt"
            good.write_text("good")
            bad.write_text("bad")

            real_hash = module.sha256_file

            def flaky_hash(path):
                if path.name == "bad.txt":
                    raise PermissionError("simulated unreadable artifact")
                return real_hash(path)

            with mock.patch.object(module, "sha256_file", side_effect=flaky_hash):
                artifacts, errors = module.snapshot_artifacts([root], work)

            self.assertEqual([item["path"] for item in artifacts], ["artifacts/good.txt"])
            self.assertEqual(
                errors,
                [{"path": "artifacts/bad.txt", "error_type": "PermissionError"}],
            )

    def test_concurrent_artifact_mutation_is_partial_scan_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            root = work / "artifacts"
            root.mkdir()
            changing = root / "changing.txt"
            changing.write_text("before")

            real_hash = module.sha256_file

            def mutate_after_hash(path):
                digest = real_hash(path)
                path.write_text("after-and-longer")
                return digest

            with mock.patch.object(module, "sha256_file", side_effect=mutate_after_hash):
                artifacts, errors = module.snapshot_artifacts([root], work)

            self.assertEqual(artifacts, [])
            self.assertEqual(
                errors,
                [{"path": "artifacts/changing.txt", "error_type": "CONCURRENT_MODIFICATION"}],
            )

    def test_scanner_exception_becomes_partial_evidence_not_wrapper_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            with mock.patch.object(
                module,
                "snapshot_artifacts",
                side_effect=RuntimeError("simulated scanner defect"),
            ):
                artifacts, errors = module.safe_snapshot_artifacts([], work)

            self.assertEqual(artifacts, [])
            self.assertEqual(
                errors,
                [{"path": ".", "error_type": "SCANNER_RuntimeError"}],
            )

    def test_validator_rejects_stale_terminal_heartbeat_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            code = (
                "import pathlib;"
                "pathlib.Path('artifacts').mkdir();"
                "pathlib.Path('artifacts/payload.txt').write_text('payload')"
            )
            result = self.run_helper(work, [sys.executable, "-c", code])
            self.assertEqual(result.returncode, 0, result.stderr)

            heartbeat_path = work / "telemetry/heartbeat.jsonl"
            lines = [json.loads(line) for line in heartbeat_path.read_text().splitlines()]
            lines[-1]["execution_status"] = "RUNNING"
            heartbeat_path.write_text(
                "".join(json.dumps(line, sort_keys=True) + "\n" for line in lines)
            )

            validated = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "validate",
                    "--checkpoint",
                    str(work / "telemetry/execution-checkpoint.json"),
                    "--heartbeat",
                    str(heartbeat_path),
                    "--root",
                    str(work),
                    "--expected-execution-status",
                    "SUCCEEDED",
                    "--expected-lifecycle-state",
                    "ARTIFACT_PROVENANCE",
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(validated.returncode, 0)
            self.assertIn(
                "HEARTBEAT_CHECKPOINT_STATE_MISMATCH",
                validated.stderr + validated.stdout,
            )

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
