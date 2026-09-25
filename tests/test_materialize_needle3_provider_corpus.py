import hashlib
import json
import pathlib
import tempfile
import unittest

from scripts.materialize_needle3_provider_corpus import (
    atomic_publish,
    load_frozen_manifest,
    load_sources,
    prepare_tmp_corpus,
    validate_materialization_paths,
    validate_session_search_runtime,
)


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
                validate_session_search_runtime(
                    runtime, manifest, observed_head="a" * 40, observed_status=""
                ),
                "a" * 40,
            )
            with self.assertRaisesRegex(RuntimeError, "SESSION_SEARCH_RUNTIME_DIRTY"):
                validate_session_search_runtime(
                    runtime, manifest, observed_head="a" * 40, observed_status=" M session_search/corpus_store.py"
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


class MaterializerGuardTests(unittest.TestCase):
    def test_preexisting_tmp_corpus_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td) / "tmp-corpus"
            tmp.mkdir()
            (tmp / "stale").write_text("old")
            with self.assertRaisesRegex(RuntimeError, "TMP_CORPUS_PREEXISTS"):
                prepare_tmp_corpus(tmp)

    def test_tmp_and_publish_namespace_must_be_disjoint(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            tmp = root / "tmp"
            with self.assertRaisesRegex(RuntimeError, "MATERIALIZATION_PATH_COLLISION"):
                validate_materialization_paths(tmp, tmp / "publish")
            with self.assertRaisesRegex(RuntimeError, "MATERIALIZATION_PATH_COLLISION"):
                validate_materialization_paths(tmp / "child", tmp)

            publish = root / "foo"
            receipt = root / "foo.receipt.json"
            receipt_tmp = root / "foo.receipt.json.tmp"
            lock = root / ".foo.runner.lock"
            for reserved in (receipt, receipt_tmp, lock):
                with self.subTest(reserved=reserved.name):
                    with self.assertRaisesRegex(RuntimeError, "MATERIALIZATION_PATH_COLLISION"):
                        validate_materialization_paths(reserved, publish)

    def test_atomic_publish_verifies_staging_before_install(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            source = root / "source"
            source.mkdir()
            (source / "corpus.sqlite3").write_bytes(b"fixture")
            destination = root / "published"
            calls = []

            def verifier(path):
                calls.append(path)
                return {"status": "DEGRADED"}

            with self.assertRaisesRegex(RuntimeError, "STAGED_CORPUS_VERIFY_FAILED"):
                atomic_publish(source, destination, verifier)
            self.assertFalse(destination.exists())
            self.assertEqual(len(calls), 1)

    def test_manifest_digest_is_bound_to_single_read_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "manifest.json"
            write_manifest(path, "chatgpt-export", [])
            raw, manifest, digest = load_frozen_manifest(path)
            path.write_text('{"changed":true}')
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
            self.assertEqual(manifest["schema_version"], "theseus.needle3.frozen_provider_artifacts.v1")
            self.assertNotEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
