#!/usr/bin/env python3
from __future__ import annotations

import argparse
from fractions import Fraction
import json
import pathlib

SUPPORTED_PRECISE_SPECIAL_FUNCTIONS = {
    "gamma", "riemann_zeta", "bessel_j", "bessel_y", "bessel_i", "bessel_k",
    "hyp2f1", "elliptic_k", "elliptic_e",
}


def evaluate_acceptance(x: dict) -> dict:
    train_acc = Fraction(int(x["train_correct"]), int(x["train_total"]))
    dominant = Fraction(int(x["dominant_decision_count"]), int(x["valid_heldout_route_calls"]))
    improvement = int(x["replica_heldout_correct"]) - int(x["base_heldout_correct"])
    checks = {
        "heldout_improvement": improvement >= 6,
        "train_accuracy": train_acc >= Fraction(7, 10),
        "reachability_degradation": int(x["replica_route_calls"]) >= int(x["base_route_calls"]) - 3,
        "negative_no_call_degradation": int(x["replica_negative_no_call"]) >= int(x["base_negative_no_call"]) - 2,
        "dominant_decision_cap": dominant <= Fraction(7, 10),
    }
    return {
        "checks": checks,
        "all_pass": all(checks.values()),
        "heldout_improvement_count": improvement,
        "train_accuracy_fraction": f"{train_acc.numerator}/{train_acc.denominator}",
        "dominant_fraction": f"{dominant.numerator}/{dominant.denominator}",
        "authority": "LOCAL_DISCRETE_ACCEPTANCE_WITNESS",
    }


def classify_special_functions_applicability(claim: dict) -> dict:
    required = sorted(set(claim.get("required_special_functions") or []))
    unknown = sorted(set(required) - SUPPORTED_PRECISE_SPECIAL_FUNCTIONS)
    supported = sorted(set(required) & SUPPORTED_PRECISE_SPECIAL_FUNCTIONS)
    if unknown:
        disposition = "UNSUPPORTED_SPECIAL_FUNCTION_REQUIREMENT"
    elif supported:
        disposition = "APPLICABLE"
    else:
        disposition = "NOT_APPLICABLE"
    return {
        "disposition": disposition,
        "required_special_functions": required,
        "supported_matches": supported,
        "unknown_requirements": unknown,
        "authority": "APPLICABILITY_ONLY",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--claim", type=pathlib.Path, required=True)
    p.add_argument("--output", type=pathlib.Path)
    args = p.parse_args()
    claim = json.loads(args.claim.read_text(encoding="utf-8"))
    receipt = {
        "schema_version": "theseus.needle.stage_b_sidecar_receipt.v1",
        "claim_id": claim["claim_id"],
        "local_acceptance": evaluate_acceptance(claim["inputs"]),
        "precise_special_functions": classify_special_functions_applicability(claim),
        "scope_note": claim["does_not_establish"],
    }
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
