import hashlib
import json
import pathlib
import tempfile
import unittest

from scripts.materialize_needle3_provider_corpus import load_sources, validate_session_search_runtime


def write_artifact(root: pathlib.Path, payload: bytes) -> tuple[str, pathlib.Path]:
    sha = hashlib.sha256(payload).hexdigest()
    path = root / "artifacts" / "sha256" / f"{sha}.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return sha, path


def write_accepted(root: pathlib.Path, name: str, sha: str, adapter: str) -> None:
    ledger = root / "ledger" / "accepted"
    ledger.mkdir(parents=True, exist_ok=True)
    (ledger / f"{name}.json").write_text(
        json.dumps({"artifact_sha256": sha, "source_adapter": adapter})
    )


def write_manifest(path: pathlib.Path, adapter: str, artifacts: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "theseus.needle3.frozen_provider_artifacts.v1",
                "session_search_runtime_sha": "a" * 40,
                "providers": {
                    "chatgpt": {
                        "source_adapter": adapter,
                        "artifact_count": len(artifacts),
                        "total_bytes": sum(item["size_bytes"] for item in artifacts),
                        "artifacts": artifacts,
                    }
                },
            }
        )
    )


class FrozenSourceSelectionTests(unittest.TestCase):
    def test_frozen_manifest_excludes_newer_accepted_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            frozen_sha, frozen_path = write_artifact(root, b"frozen")
            newer_sha, _ = write_artifact(root, b"newer")
            write_accepted(root, "frozen", frozen_sha, "chatgpt-export")
            write_accepted(root, "newer", newer_sha, "chatgpt-export")
            manifest = root / "frozen.json"
            write_manifest(
                manifest,
                "chatgpt-export",
                [{"sha256": frozen_sha, "size_bytes": frozen_path.stat().st_size}],
            )

            selected = load_sources(root, manifest, "chatgpt-export")

            self.assertEqual(selected, [frozen_path])


    def test_session_search_runtime_must_match_frozen_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            runtime = root / "runtime"
            runtime.mkdir()
            manifest = root / "frozen.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "theseus.needle3.frozen_provider_artifacts.v1",
                        "session_search_runtime_sha": "a" * 40,
                        "providers": {},
                    }
                )
            )
            with self.assertRaisesRegex(RuntimeError, "SESSION_SEARCH_RUNTIME_SHA_MISMATCH"):
                validate_session_search_runtime(runtime, manifest, observed_head="b" * 40)

            self.assertEqual(
                validate_session_search_runtime(runtime, manifest, observed_head="a" * 40),
                "a" * 40,
            )

    def test_frozen_manifest_missing_or_mismatched_artifact_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            payload = b"frozen"
            sha, path = write_artifact(root, payload)
            manifest = root / "frozen.json"
            write_manifest(
                manifest,
                "chatgpt-export",
                [{"sha256": sha, "size_bytes": len(payload)}],
            )

            path.unlink()
            with self.assertRaisesRegex(RuntimeError, "FROZEN_ARTIFACT_MISSING"):
                load_sources(root, manifest, "chatgpt-export")

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"tampered")
            with self.assertRaisesRegex(RuntimeError, "FROZEN_ARTIFACT_SIZE_MISMATCH|FROZEN_ARTIFACT_HASH_MISMATCH"):
                load_sources(root, manifest, "chatgpt-export")


if __name__ == "__main__":
    unittest.main()
