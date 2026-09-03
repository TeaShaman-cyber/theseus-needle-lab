#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib

from scipy.stats import fisher_exact


def diagnostic(inputs: dict) -> dict:
    base_correct = int(inputs["base_heldout_correct"])
    replica_correct = int(inputs["replica_heldout_correct"])
    total = 72
    table = [
        [replica_correct, total - replica_correct],
        [base_correct, total - base_correct],
    ]
    result = fisher_exact(table, alternative="greater")
    return {
        "authority": "DIAGNOSTIC_ONLY",
        "method": "scipy.stats.fisher_exact",
        "alternative": "greater",
        "table": table,
        "odds_ratio": float(result.statistic),
        "p_value": float(result.pvalue),
        "does_not_establish": "This diagnostic is not part of the preregistered Stage B acceptance authority and cannot rescue or reject a model result by itself.",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--claim", type=pathlib.Path, required=True)
    p.add_argument("--output", type=pathlib.Path)
    args = p.parse_args()
    claim = json.loads(args.claim.read_text(encoding="utf-8"))
    receipt = {
        "schema_version": "theseus.needle.stage_b_scipy_diagnostic.v1",
        "claim_id": claim["claim_id"],
        "scipy": diagnostic(claim["inputs"]),
    }
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
