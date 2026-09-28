#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import re
import subprocess
from typing import Any

CONFIG_SCHEMA = "needle-external-typed-decision-witness-config-v1"
RECEIPT_SCHEMA = "needle-external-typed-decision-witness-v1"
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA64_RE = re.compile(r"^[0-9a-f]{64}$")


def load_json(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def total_variation(left: dict[str, float], right: dict[str, float]) -> float:
    if set(left) != set(right) or len(left) < 2:
        raise ValueError("probability option-set mismatch")
    left_values = {}
    right_values = {}
    for option_id in sorted(left):
        for source, target in ((left, left_values), (right, right_values)):
            value = source[option_id]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("probability must be numeric")
            value = float(value)
            if not math.isfinite(value) or value < 0.0 or value > 1.0:
                raise ValueError("probability out of range")
            target[option_id] = value
    if not math.isclose(math.fsum(left_values.values()), 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("left probabilities not normalized")
    if not math.isclose(math.fsum(right_values.values()), 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("right probabilities not normalized")
    return 0.5 * math.fsum(
        abs(left_values[key] - right_values[key])
        for key in sorted(left_values)
    )


def git_head(path: pathlib.Path) -> str:
    value = subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    if not SHA40_RE.fullmatch(value):
        raise ValueError("invalid source git HEAD")
    return value


def _authority_false(value: dict[str, Any], *, prefix: str) -> None:
    for key in (
        "acceptance_authority",
        "permission_authority",
        "verification_authority",
        "promotion_authority",
    ):
        if value.get(key) is not False:
            raise ValueError(f"{prefix} authority boundary violated: {key}")


def _source_files(
    config: dict[str, Any],
    source_root: pathlib.Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    source = config["source"]
    loaded = {}
    provenance = []
    for key in ("manifest", "candidate_receipt", "comparison_receipt"):
        spec = source[key]
        rel = pathlib.Path(spec["path"])
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"unsafe source path: {key}")
        path = source_root / rel
        observed = sha256_file(path)
        if observed != spec["sha256"]:
            raise ValueError(f"source hash mismatch: {key}")
        loaded[key] = load_json(path)
        provenance.append(
            {
                "kind": key,
                "path": spec["path"],
                "sha256": observed,
            }
        )
    return (
        loaded["manifest"],
        loaded["candidate_receipt"],
        loaded["comparison_receipt"],
        provenance,
    )


def _validate_config(config: dict[str, Any]) -> None:
    if config.get("schema") != CONFIG_SCHEMA:
        raise ValueError("unsupported witness config schema")
    if config.get("claim_scope") != "BOUNDED_TYPED_DECISION_WITNESS_ONLY":
        raise ValueError("unexpected claim scope")
    if config.get("metric") != "TOTAL_VARIATION":
        raise ValueError("unsupported witness metric")
    if config.get("probability_surface") != "L0":
        raise ValueError("unsupported probability surface")
    if config.get("mapped_state") != "MODEL_OR_DOMAIN_WITNESS":
        raise ValueError("unexpected mapped state")
    if config.get("semantic_oracle") is not False:
        raise ValueError("semantic oracle must be false")
    if config.get("scientific_acceptance_performed") is not False:
        raise ValueError("scientific acceptance must be false")
    _authority_false(config, prefix="config")

    source = config.get("source")
    if not isinstance(source, dict):
        raise ValueError("source config missing")
    for key in ("storage_revision", "experiment_revision"):
        if not SHA40_RE.fullmatch(str(source.get(key, ""))):
            raise ValueError(f"invalid source {key}")
    if not isinstance(source.get("run_id"), str) or not source["run_id"]:
        raise ValueError("invalid source run_id")

    comparisons = config.get("comparisons")
    if not isinstance(comparisons, list) or len(comparisons) != 2:
        raise ValueError("exactly two comparisons are required")
    expected_pairs = {
        ("S0_ORIGINAL", "S2_FORMAT_PRESERVE", "SAME"),
        ("S0_ORIGINAL", "S3_SEMANTIC_CHANGE_CONTROL", "CHANGED_CONTROL"),
    }
    observed_pairs = {
        (
            row.get("reference_surface"),
            row.get("candidate_surface"),
            row.get("declared_semantic_relation"),
        )
        for row in comparisons
        if isinstance(row, dict)
    }
    if observed_pairs != expected_pairs:
        raise ValueError("comparison config does not match preregistered pair set")


def _manifest_semantics(manifest: dict[str, Any]) -> dict[str, str]:
    if manifest.get("schema") != "theseus.anyjev-hbr1-manifest.v1":
        raise ValueError("external manifest schema mismatch")
    if manifest.get("outcome_escrow_in_candidate_input") is not False:
        raise ValueError("manifest outcome escrow boundary violated")
    _authority_false(manifest, prefix="manifest")

    rows = manifest.get("surfaces")
    if not isinstance(rows, list):
        raise ValueError("manifest surfaces missing")
    semantics = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid manifest surface")
        surface_id = row.get("surface_id")
        expected = row.get("expected_semantics")
        if surface_id in semantics:
            raise ValueError("duplicate manifest surface")
        if not isinstance(surface_id, str) or expected not in {"SAME", "CHANGED"}:
            raise ValueError("invalid manifest surface semantics")
        semantics[surface_id] = expected
    return semantics


def _candidate_l0(
    candidate: dict[str, Any],
    config: dict[str, Any],
    manifest_sha256: str,
) -> dict[str, dict[str, float]]:
    source = config["source"]
    if candidate.get("schema") != "theseus.anyjev-hbr1-candidate.v1":
        raise ValueError("candidate receipt schema mismatch")
    if candidate.get("repository_sha") != source["experiment_revision"]:
        raise ValueError("candidate experiment revision mismatch")
    if str(candidate.get("run_id")) != source["run_id"]:
        raise ValueError("candidate run id mismatch")
    if candidate.get("outcome_escrow_consumed") is not False:
        raise ValueError("candidate consumed outcome escrow")
    if candidate.get("calibration_claim") is not False:
        raise ValueError("candidate calibration claim must be false")
    if candidate.get("jev_equivalence_claim") is not False:
        raise ValueError("candidate Jev-equivalence claim must be false")
    _authority_false(candidate, prefix="candidate")

    manifest_ref = candidate.get("manifest")
    if not isinstance(manifest_ref, dict) or manifest_ref.get("sha256") != manifest_sha256:
        raise ValueError("candidate manifest binding mismatch")

    required = {"S0_ORIGINAL", "S2_FORMAT_PRESERVE", "S3_SEMANTIC_CHANGE_CONTROL"}
    result = {}
    for row in candidate.get("results", []):
        if not isinstance(row, dict):
            raise ValueError("invalid candidate result")
        if row.get("requested_level") != "L0":
            continue
        surface_id = row.get("surface_id")
        if surface_id not in required:
            continue
        if surface_id in result:
            raise ValueError("duplicate L0 surface result")
        if row.get("served_level") != "L0":
            raise ValueError("L0 served-level mismatch")
        option_ids = row.get("option_ids")
        probs = row.get("probabilities")
        if not isinstance(option_ids, list) or len(option_ids) != len(set(option_ids)):
            raise ValueError("invalid option id list")
        if not isinstance(probs, dict) or set(probs) != set(option_ids):
            raise ValueError("probability option-set mismatch")
        validated = {key: float(value) for key, value in probs.items()}
        total_variation(validated, validated)
        result[surface_id] = validated

    if set(result) != required:
        raise ValueError("missing required L0 surface result")
    return result


def build_witness(
    config: dict[str, Any],
    source_root: pathlib.Path,
    *,
    source_revision: str,
    implementation_sha: str,
) -> dict[str, Any]:
    _validate_config(config)
    if source_revision != config["source"]["storage_revision"]:
        raise ValueError("external source storage revision mismatch")
    if not SHA40_RE.fullmatch(implementation_sha):
        raise ValueError("invalid Needle implementation SHA")

    manifest, candidate, comparison, provenance = _source_files(config, source_root)
    semantics = _manifest_semantics(manifest)

    manifest_sha = config["source"]["manifest"]["sha256"]
    candidate_sha = config["source"]["candidate_receipt"]["sha256"]
    comparison_sha = config["source"]["comparison_receipt"]["sha256"]

    l0 = _candidate_l0(candidate, config, manifest_sha)

    if comparison.get("schema") != "theseus.anyjev-hbr1-comparison.v1":
        raise ValueError("comparison receipt schema mismatch")
    if comparison.get("candidate_receipt_sha256") != candidate_sha:
        raise ValueError("comparison candidate binding mismatch")
    if comparison.get("source_repository_sha") != config["source"]["experiment_revision"]:
        raise ValueError("comparison source revision mismatch")
    if str(comparison.get("source_run_id")) != config["source"]["run_id"]:
        raise ValueError("comparison source run mismatch")
    authority = comparison.get("authority")
    required_authority = {"acceptance", "outcome_is_label", "promotion", "verification"}
    if (
        not isinstance(authority, dict)
        or set(authority) != required_authority
        or any(value is not False for value in authority.values())
    ):
        raise ValueError("comparison authority boundary violated")

    stored_l0 = (
        comparison.get("surface_total_variation_from_S0", {})
        .get("L0", {})
    )

    witness_rows = []
    for row in config["comparisons"]:
        ref = row["reference_surface"]
        candidate_surface = row["candidate_surface"]
        relation = row["declared_semantic_relation"]

        ref_semantics = semantics.get(ref)
        candidate_semantics = semantics.get(candidate_surface)
        if ref_semantics != "SAME":
            raise ValueError("reference surface semantics mismatch")
        if relation == "SAME":
            if candidate_semantics != "SAME":
                raise ValueError("SAME relation disagrees with external manifest")
        elif relation == "CHANGED_CONTROL":
            if candidate_semantics != "CHANGED":
                raise ValueError("CHANGED_CONTROL relation disagrees with external manifest")
        else:
            raise ValueError("unsupported declared semantic relation")

        observed = total_variation(l0[ref], l0[candidate_surface])
        source_value = stored_l0.get(candidate_surface)
        if isinstance(source_value, bool) or not isinstance(source_value, (int, float)):
            raise ValueError("source comparison value missing")
        if not math.isclose(observed, float(source_value), rel_tol=0.0, abs_tol=1e-15):
            raise ValueError("recomputed TV differs from source comparison receipt")

        witness_rows.append(
            {
                "reference_surface": ref,
                "candidate_surface": candidate_surface,
                "declared_semantic_relation": relation,
                "metric": "TOTAL_VARIATION",
                "observed_value": observed,
                "source_comparison_value": float(source_value),
                "probability_surface": "L0",
            }
        )

    return {
        "schema": RECEIPT_SCHEMA,
        "claim_scope": config["claim_scope"],
        "implementation_sha": implementation_sha,
        "mapped_state": "MODEL_OR_DOMAIN_WITNESS",
        "source": {
            "repository": config["source"]["repository"],
            "storage_revision": source_revision,
            "experiment_revision": config["source"]["experiment_revision"],
            "run_id": config["source"]["run_id"],
            "files": provenance,
        },
        "metric": "TOTAL_VARIATION",
        "probability_surface": "L0",
        "comparisons": witness_rows,
        "comparison_context": "REPRESENTATION_VS_PREREGISTERED_SEMANTIC_CONTROL_SENSITIVITY",
        "model_or_domain_witness": True,
        "semantic_oracle": False,
        "scientific_acceptance_performed": False,
        "acceptance_authority": False,
        "permission_authority": False,
        "verification_authority": False,
        "promotion_authority": False,
    }


def validate_witness(
    receipt: dict[str, Any],
    config: dict[str, Any],
    source_root: pathlib.Path,
    *,
    source_revision: str,
    implementation_sha: str,
) -> None:
    expected = build_witness(
        config,
        source_root,
        source_revision=source_revision,
        implementation_sha=implementation_sha,
    )
    if receipt != expected:
        raise ValueError("witness receipt does not match exact recomputation")


def write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Build or validate the bounded external AnyJev HBR-1 Needle witness."
    )
    sub = result.add_subparsers(dest="command", required=True)
    for name in ("build", "validate"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--config", type=pathlib.Path, required=True)
        cmd.add_argument("--source-root", type=pathlib.Path, required=True)
        cmd.add_argument("--implementation-sha", required=True)
        if name == "build":
            cmd.add_argument("--output", type=pathlib.Path, required=True)
        else:
            cmd.add_argument("--receipt", type=pathlib.Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    config = load_json(args.config)
    source_revision = git_head(args.source_root)
    if args.command == "build":
        receipt = build_witness(
            config,
            args.source_root,
            source_revision=source_revision,
            implementation_sha=args.implementation_sha,
        )
        write_json(args.output, receipt)
        print("EXTERNAL_TYPED_DECISION_WITNESS=BUILT STATE=MODEL_OR_DOMAIN_WITNESS")
        return 0

    receipt = load_json(args.receipt)
    validate_witness(
        receipt,
        config,
        args.source_root,
        source_revision=source_revision,
        implementation_sha=args.implementation_sha,
    )
    print("EXTERNAL_TYPED_DECISION_WITNESS_VALID=PASS STATE=MODEL_OR_DOMAIN_WITNESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
