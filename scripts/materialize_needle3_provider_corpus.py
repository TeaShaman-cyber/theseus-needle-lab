#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

SCHEMA = "theseus.needle3.provider_corpus_materialization.v1"


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_sources(
    source_corpus: pathlib.Path,
    frozen_manifest: pathlib.Path,
    adapter: str,
) -> list[pathlib.Path]:
    manifest = json.loads(frozen_manifest.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "theseus.needle3.frozen_provider_artifacts.v1":
        raise RuntimeError("UNSUPPORTED_FROZEN_MANIFEST_SCHEMA")
    providers = manifest.get("providers")
    if not isinstance(providers, dict):
        raise RuntimeError("INVALID_FROZEN_MANIFEST_PROVIDERS")

    matches = [
        (name, provider)
        for name, provider in providers.items()
        if isinstance(provider, dict) and provider.get("source_adapter") == adapter
    ]
    if len(matches) != 1:
        raise RuntimeError("FROZEN_PROVIDER_ADAPTER_MATCH_NOT_UNIQUE")
    _, provider = matches[0]
    frozen_artifacts = provider.get("artifacts")
    if not isinstance(frozen_artifacts, list) or not frozen_artifacts:
        raise RuntimeError("NO_FROZEN_PROVIDER_ARTIFACTS")
    if provider.get("artifact_count") != len(frozen_artifacts):
        raise RuntimeError("FROZEN_ARTIFACT_COUNT_MISMATCH")

    artifacts_root = source_corpus / "artifacts" / "sha256"
    result: list[pathlib.Path] = []
    total_bytes = 0
    for item in frozen_artifacts:
        if not isinstance(item, dict):
            raise RuntimeError("INVALID_FROZEN_ARTIFACT_ENTRY")
        sha = item.get("sha256")
        size_bytes = item.get("size_bytes")
        if not isinstance(sha, str) or len(sha) != 64:
            raise RuntimeError("INVALID_FROZEN_ARTIFACT_SHA")
        if not isinstance(size_bytes, int) or size_bytes < 0:
            raise RuntimeError("INVALID_FROZEN_ARTIFACT_SIZE")
        artifact = artifacts_root / f"{sha}.zip"
        if not artifact.is_file():
            raise RuntimeError(f"FROZEN_ARTIFACT_MISSING:{sha}")
        observed_size = artifact.stat().st_size
        if observed_size != size_bytes:
            raise RuntimeError(f"FROZEN_ARTIFACT_SIZE_MISMATCH:{sha}")
        if sha256_file(artifact) != sha:
            raise RuntimeError(f"FROZEN_ARTIFACT_HASH_MISMATCH:{sha}")
        total_bytes += observed_size
        result.append(artifact)

    if provider.get("total_bytes") != total_bytes:
        raise RuntimeError("FROZEN_PROVIDER_TOTAL_BYTES_MISMATCH")
    return result


def validate_session_search_runtime(
    session_search_root: pathlib.Path,
    frozen_manifest: pathlib.Path,
    *,
    observed_head: str | None = None,
) -> str:
    manifest = json.loads(frozen_manifest.read_text(encoding="utf-8"))
    expected = manifest.get("session_search_runtime_sha")
    if not isinstance(expected, str) or len(expected) != 40:
        raise RuntimeError("INVALID_SESSION_SEARCH_RUNTIME_SHA")
    head = observed_head or subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=session_search_root, text=True
    ).strip()
    if head != expected:
        raise RuntimeError(f"SESSION_SEARCH_RUNTIME_SHA_MISMATCH:expected={expected}:observed={head}")
    return head


def import_session_search(root: pathlib.Path):
    sys.path.insert(0, str(root))
    from session_search.corpus_store import ingest_many, verify_corpus  # type: ignore
    return ingest_many, verify_corpus


def atomic_publish(source: pathlib.Path, destination: pathlib.Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = pathlib.Path(tempfile.mkdtemp(prefix=f".{destination.name}.publish-", dir=destination.parent))
    staged = staging / destination.name
    try:
        shutil.copytree(source, staged, symlinks=False)
        if destination.exists():
            raise RuntimeError("PUBLISH_DESTINATION_EXISTS")
        os.replace(staged, destination)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source-corpus", required=True, type=pathlib.Path)
    p.add_argument("--source-adapter", required=True)
    p.add_argument("--tmp-corpus", required=True, type=pathlib.Path)
    p.add_argument("--publish-corpus", required=True, type=pathlib.Path)
    p.add_argument("--session-search-root", required=True, type=pathlib.Path)
    p.add_argument("--frozen-manifest", required=True, type=pathlib.Path)
    args = p.parse_args()

    lock_path = args.publish_corpus.parent / f".{args.publish_corpus.name}.runner.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("MATERIALIZE BLOCKED reason=RUNNER_ACTIVE")
            return 75

        session_search_head = validate_session_search_runtime(
            args.session_search_root, args.frozen_manifest
        )
        ingest_many, verify_corpus = import_session_search(args.session_search_root)
        sources = load_sources(args.source_corpus, args.frozen_manifest, args.source_adapter)
        args.tmp_corpus.mkdir(parents=True, exist_ok=True)

        mutation_lock = args.tmp_corpus / "mutation.lock"
        if mutation_lock.exists():
            print("MATERIALIZE BLOCKED reason=TMP_CORPUS_MUTATION_ACTIVE")
            return 75

        result = ingest_many(sources, args.tmp_corpus)
        if result.get("status") != "COMPLETE":
            print(json.dumps({"status": "DEGRADED", "ingest": result.get("batch_verification")}, sort_keys=True))
            return 1

        verification = verify_corpus(args.tmp_corpus)
        if verification.get("status") != "VERIFIED":
            print(json.dumps({"status": "DEGRADED", "verify": verification}, sort_keys=True))
            return 1

        if args.publish_corpus.exists():
            print("MATERIALIZE BLOCKED reason=PUBLISH_DESTINATION_EXISTS")
            return 75

        atomic_publish(args.tmp_corpus, args.publish_corpus)
        published_verify = verify_corpus(args.publish_corpus)
        if published_verify.get("status") != "VERIFIED":
            raise RuntimeError("PUBLISHED_CORPUS_VERIFY_FAILED")

        db = args.publish_corpus / "corpus.sqlite3"
        receipt = {
            "schema": SCHEMA,
            "published_at": utc_now(),
            "source_adapter": args.source_adapter,
            "source_artifact_count": len(sources),
            "session_search_root": str(args.session_search_root),
            "session_search_head": session_search_head,
            "published_corpus": str(args.publish_corpus),
            "published_corpus_db_sha256": sha256_file(db),
            "verification": published_verify,
        }
        receipt["frozen_manifest_sha256"] = sha256_file(args.frozen_manifest)
        receipt_path = args.publish_corpus.parent / f"{args.publish_corpus.name}.receipt.json"
        tmp_receipt = receipt_path.with_suffix(receipt_path.suffix + ".tmp")
        tmp_receipt.write_bytes(stable_json(receipt) + b"\n")
        os.replace(tmp_receipt, receipt_path)
        if json.loads(receipt_path.read_text(encoding="utf-8")) != receipt:
            raise RuntimeError("RECEIPT_READBACK_MISMATCH")

        print(json.dumps({"status": "VERIFIED", "receipt": str(receipt_path), "verification": published_verify}, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
