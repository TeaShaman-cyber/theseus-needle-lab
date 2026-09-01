import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class CollectCliTests(unittest.TestCase):
    def test_main_passes_second_precision_window_start_to_source_collection(self):
        project_root = Path(__file__).resolve().parents[1]
        script = project_root / "scripts" / "collect-needle-watch.py"
        spec = importlib.util.spec_from_file_location("needle_watch_collect_cli", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        captured = {}

        def fake_load_source_data(args, observed_at, since_value):
            captured["since"] = since_value
            return [], [{
                "source_id": "fixture:healthy",
                "status": "ok",
                "checked_at": observed_at,
                "records_seen": 0,
                "total_count": 0,
                "returned_count": 0,
                "incomplete_results": False,
                "truncated": False,
                "cursor_or_watermark": since_value,
                "error_class": None,
            }]

        module.load_source_data = fake_load_source_data
        with TemporaryDirectory() as tmp:
            old_argv = sys.argv
            old_now = os.environ.get("NEEDLE_WATCH_NOW")
            try:
                sys.argv = [str(script), "--repo-root", tmp]
                os.environ["NEEDLE_WATCH_NOW"] = "2026-09-01T12:29:24Z"
                self.assertEqual(module.main(), 0)
            finally:
                sys.argv = old_argv
                if old_now is None:
                    os.environ.pop("NEEDLE_WATCH_NOW", None)
                else:
                    os.environ["NEEDLE_WATCH_NOW"] = old_now

        self.assertEqual(captured["since"], "2026-08-31T12:29:24Z")

    def test_local_fallback_run_id_is_unique_within_same_day(self):
        project_root = Path(__file__).resolve().parents[1]
        script = project_root / "scripts" / "collect-needle-watch.py"
        config = project_root / "config" / "needle-watch.json"
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            fixture = repo_root / "fixture.json"
            fixture.write_text(json.dumps({
                "source_health": [{
                    "source_id": "fixture:healthy",
                    "status": "ok",
                    "checked_at": "2026-09-01T12:00:00Z",
                    "records_seen": 0,
                    "total_count": 0,
                    "returned_count": 0,
                    "incomplete_results": False,
                    "truncated": False,
                    "cursor_or_watermark": "2026-08-31T12:00:00Z",
                    "error_class": None,
                }],
                "candidates": [],
            }))
            env = os.environ.copy()
            env.pop("NEEDLE_WATCH_RUN_ID", None)
            env.pop("GITHUB_RUN_ID", None)
            env.update({
                "NEEDLE_WATCH_COLLECTOR_REVISION": "d" * 40,
                "PYTHONDONTWRITEBYTECODE": "1",
            })
            run_ids = []
            for now in ("2026-09-01T12:00:00Z", "2026-09-01T13:00:00Z"):
                env["NEEDLE_WATCH_NOW"] = now
                result = subprocess.run(
                    [sys.executable, str(script), "--repo-root", str(repo_root),
                     "--config", str(config), "--fixture-source", str(fixture)],
                    cwd=project_root, env=env, text=True, capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                latest = json.loads((repo_root / "data" / "latest" / "needle-watch.json").read_text())
                run_ids.append(latest["run_id"])
            self.assertNotEqual(run_ids[0], run_ids[1])
            self.assertEqual(len(list((repo_root / "data" / "runs").glob("*.json"))), 2)

    def test_fixture_mode_marks_same_entity_seen_from_previous_latest_snapshot(self):
        project_root = Path(__file__).resolve().parents[1]
        script = project_root / "scripts" / "collect-needle-watch.py"
        config = project_root / "config" / "needle-watch.json"
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            latest = repo_root / "data" / "latest" / "needle-watch.json"
            latest.parent.mkdir(parents=True)
            latest.write_text(json.dumps({
                "candidates": [{
                    "candidate_id": "0" * 64,
                    "source_entity_id": "github-repo:123456",
                }]
            }))
            fixture = repo_root / "fixture.json"
            fixture.write_text(json.dumps({
                "source_health": [{
                    "source_id": "fixture:healthy",
                    "status": "ok",
                    "checked_at": "2026-09-01T12:00:00Z",
                    "records_seen": 1,
                    "total_count": 1,
                    "returned_count": 1,
                    "incomplete_results": False,
                    "truncated": False,
                    "cursor_or_watermark": "2026-08-31T12:00:00Z",
                    "error_class": None,
                }],
                "candidates": [{
                    "source_id": "github-search:tiny-model",
                    "source_class": "github_repo",
                    "source_entity_id": "github-repo:123456",
                    "canonical_url": "https://github.com/example/project",
                    "title": "Example Project",
                    "observed_at": "2026-09-01T12:00:00Z",
                    "published_or_pushed_at": "2026-09-01T11:00:00Z",
                    "source_identity": "example/project@main",
                    "upstream_revision": "f" * 40,
                    "discovery_route": "github_search:tiny-model",
                    "matched_watch_lines": ["tiny-model"],
                    "content_fingerprint": "commit:" + "f" * 40,
                }],
            }))
            env = os.environ.copy()
            env.update({
                "NEEDLE_WATCH_NOW": "2026-09-01T12:00:00Z",
                "NEEDLE_WATCH_RUN_ID": "fixture-run-seen",
                "NEEDLE_WATCH_COLLECTOR_REVISION": "d" * 40,
                "PYTHONDONTWRITEBYTECODE": "1",
            })
            result = subprocess.run(
                [sys.executable, str(script), "--repo-root", str(repo_root),
                 "--config", str(config), "--fixture-source", str(fixture)],
                cwd=project_root, env=env, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(latest.read_text())
            self.assertTrue(receipt["candidates"][0]["entity_seen_in_previous_snapshot"])
            self.assertFalse(receipt["candidates"][0]["seen_in_previous_snapshot"])

    def test_fixture_mode_writes_valid_run_daily_and_latest_receipts(self):
        project_root = Path(__file__).resolve().parents[1]
        script = project_root / "scripts" / "collect-needle-watch.py"
        config = project_root / "config" / "needle-watch.json"
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            fixture = repo_root / "fixture.json"
            fixture.write_text(json.dumps({
                "source_health": [{
                    "source_id": "fixture:healthy",
                    "status": "ok",
                    "checked_at": "2026-09-01T12:00:00Z",
                    "records_seen": 0,
                    "total_count": 0,
                    "returned_count": 0,
                    "incomplete_results": False,
                    "truncated": False,
                    "cursor_or_watermark": "2026-08-31",
                    "error_class": None,
                }],
                "candidates": [],
            }))
            env = os.environ.copy()
            env.update({
                "NEEDLE_WATCH_NOW": "2026-09-01T12:00:00Z",
                "NEEDLE_WATCH_RUN_ID": "fixture-run-1",
                "NEEDLE_WATCH_COLLECTOR_REVISION": "d" * 40,
                "PYTHONDONTWRITEBYTECODE": "1",
            })
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--repo-root",
                    str(repo_root),
                    "--config",
                    str(config),
                    "--fixture-source",
                    str(fixture),
                ],
                cwd=project_root,
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("NEEDLE_WATCH_RECEIPT PASS", result.stdout)
            run = repo_root / "data" / "runs" / "fixture-run-1.json"
            daily = repo_root / "data" / "daily" / "2026-09-01.json"
            latest = repo_root / "data" / "latest" / "needle-watch.json"
            self.assertEqual(run.read_bytes(), daily.read_bytes())
            self.assertEqual(run.read_bytes(), latest.read_bytes())
            receipt = json.loads(latest.read_text())
            self.assertEqual(receipt["run_id"], "fixture-run-1")
            self.assertEqual(receipt["collector_revision"], "d" * 40)
            self.assertEqual(receipt["candidates"], [])


if __name__ == "__main__":
    unittest.main()
