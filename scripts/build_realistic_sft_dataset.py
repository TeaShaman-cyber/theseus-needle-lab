from __future__ import annotations

import json
import pathlib
import re
from typing import Iterable

SCHEMA_CONTRACT = "needle-route-uppercase-v1"
SOURCE_KIND = "synthetic_repo_authored"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _expand_family(family: dict) -> list[dict]:
    rows: list[dict] = []
    split = str(family["split"])
    phrases = list(family["phrases"])
    entities = list(family["entities"])
    for phrase_index, phrase in enumerate(phrases, start=1):
        for entity_index, entity in enumerate(entities, start=1):
            rows.append(
                {
                    "case_id": f"{split}-{_slug(family['family_id'])}-p{phrase_index:02d}-e{entity_index:02d}",
                    "family_id": family["family_id"],
                    "split": split,
                    "applicability": family["applicability"],
                    "expected_decision": family["expected_decision"],
                    "semantic_rule": family["semantic_rule"],
                    "query": phrase.format(entity=entity),
                    "rationale": family["rationale"],
                    "derivation_family": family["derivation_family"],
                    "entity_variant": entity,
                    "schema_contract": SCHEMA_CONTRACT,
                    "source_kind": SOURCE_KIND,
                }
            )
    return rows


def _validate_unique(rows: Iterable[dict], field: str) -> None:
    values = [row[field] for row in rows]
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {field}")


def build_semantic_cases(spec: dict) -> tuple[list[dict], list[dict]]:
    if spec.get("schema_version") != "needle-stage-b-families-v1":
        raise ValueError("unsupported family schema")
    train: list[dict] = []
    heldout: list[dict] = []
    for family in spec.get("families", []):
        target = train if family.get("split") == "train" else heldout if family.get("split") == "heldout" else None
        if target is None:
            raise ValueError("invalid split")
        target.extend(_expand_family(family))

    all_rows = train + heldout
    _validate_unique(all_rows, "case_id")
    _validate_unique(all_rows, "query")
    if {row["family_id"] for row in train} & {row["family_id"] for row in heldout}:
        raise ValueError("train/heldout family overlap")
    return train, heldout


def load_family_spec(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

import argparse
import hashlib
import os
import tempfile

ROUTE_PREFIX = "Use route to classify the following evidence:\n\n"
ROUTE_SCHEMA = {
    "name": "route",
    "parameters": {
        "type": "object",
        "properties": {"decision": {"type": "string", "enum": ["PROBE", "READY", "UNKNOWN"]}},
        "required": ["decision"],
    },
    "description": "Classify the current evidence state. Always use route for this classification. PROBE = current verification is needed and safely possible. READY = current authoritative evidence verifies the state. UNKNOWN = evidence is insufficient and no safe current probe is available.",
}
TRAINING_CONFIG = {
    "cactus_needle": "2.0.8",
    "numpy_shuffle_seed": 0,
    "examples": 360,
    "val_split": 0.10,
    "batch_size": 16,
    "lr": 0.0001,
    "lora_rank": 16,
    "lora_alpha": 32,
    "max_len": 256,
    "epochs": 15,
    "generate": 0,
    "workers": 1,
}


def _stable_json_bytes(obj: object, *, newline: bool = True) -> bytes:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return raw + (b"\n" if newline else b"")


def _contract_json_bytes(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _jsonl_bytes(rows: Iterable[dict]) -> bytes:
    return b"".join(_stable_json_bytes(row) for row in rows)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def project_needle_case(record: dict, schema: dict, prefix: str) -> dict:
    if record["applicability"] == "route":
        decision = record["expected_decision"]
        if decision not in {"PROBE", "READY", "UNKNOWN"}:
            raise ValueError("invalid positive decision")
        return {
            "query": prefix + record["query"],
            "tools": [schema],
            "answers": [{"name": "route", "arguments": {"decision": decision}}],
        }
    if record["applicability"] == "none" and record["expected_decision"] is None:
        return {"query": record["query"], "tools": [schema], "answers": []}
    raise ValueError("invalid applicability/decision contract")


def _binding(path: str, data: bytes, rows: int | None = None) -> dict:
    result = {"path": path, "sha256": _sha256(data), "bytes": len(data)}
    if rows is not None:
        result["rows"] = rows
    return result


def build_outputs(spec: dict, schema: dict = ROUTE_SCHEMA, prefix: str = ROUTE_PREFIX) -> dict:
    train, heldout = build_semantic_cases(spec)
    semantic_rows = train + heldout
    train_projection = [project_needle_case(row, schema, prefix) for row in train]
    heldout_projection = [project_needle_case(row, schema, prefix) for row in heldout]

    files: dict[str, bytes] = {
        "contract/route-schema.json": _contract_json_bytes(schema),
        "contract/route-positive-prefix.txt": prefix.encode("utf-8"),
        "contract/training-config.json": _stable_json_bytes(TRAINING_CONFIG),
        "source/semantic-cases.jsonl": _jsonl_bytes(semantic_rows),
        "data/train.needle.jsonl": _jsonl_bytes(train_projection),
        "data/heldout.eval.jsonl": _jsonl_bytes(heldout_projection),
    }

    dataset_manifest = {
        "schema_version": "needle-stage-b-dataset-manifest-v1",
        "source_kind": SOURCE_KIND,
        "train_rows": len(train),
        "bindings": [
            _binding("source/semantic-cases.jsonl", files["source/semantic-cases.jsonl"], len(semantic_rows)),
            _binding("data/train.needle.jsonl", files["data/train.needle.jsonl"], len(train)),
            _binding("contract/route-schema.json", files["contract/route-schema.json"]),
            _binding("contract/route-positive-prefix.txt", files["contract/route-positive-prefix.txt"]),
            _binding("contract/training-config.json", files["contract/training-config.json"]),
        ],
    }
    heldout_manifest = {
        "schema_version": "needle-stage-b-heldout-manifest-v1",
        "source_kind": SOURCE_KIND,
        "heldout_rows": len(heldout),
        "bindings": [
            _binding("source/semantic-cases.jsonl", files["source/semantic-cases.jsonl"], len(semantic_rows)),
            _binding("data/heldout.eval.jsonl", files["data/heldout.eval.jsonl"], len(heldout)),
            _binding("contract/route-schema.json", files["contract/route-schema.json"]),
            _binding("contract/route-positive-prefix.txt", files["contract/route-positive-prefix.txt"]),
        ],
    }
    files["manifests/dataset-manifest.json"] = _stable_json_bytes(dataset_manifest)
    files["manifests/heldout-manifest.json"] = _stable_json_bytes(heldout_manifest)
    return {"files": files, "train": train, "heldout": heldout}


def _atomic_write(path: pathlib.Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def write_outputs(root: pathlib.Path, outputs: dict) -> None:
    base = root / "experiments" / "needle-realistic-sft"
    for relative, data in outputs["files"].items():
        _atomic_write(base / relative, data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deterministic Needle Stage B dataset artifacts.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    family_path = args.root / "experiments" / "needle-realistic-sft" / "source" / "families.json"
    outputs = build_outputs(load_family_spec(family_path))
    if args.write:
        write_outputs(args.root, outputs)
    print(json.dumps({"train": len(outputs["train"]), "heldout": len(outputs["heldout"]), "files": sorted(outputs["files"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
