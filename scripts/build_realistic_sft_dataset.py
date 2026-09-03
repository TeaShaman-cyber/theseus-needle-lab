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
