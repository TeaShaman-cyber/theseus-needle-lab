#!/usr/bin/env python3
import argparse
import copy
import json
import pathlib

CLASSIFICATION_PREFIX = "Use route to classify the following evidence:"
ROUTE_DESCRIPTION = (
    "Classify the current evidence state. Always use route for this classification. "
    "PROBE = current verification is needed and safely possible. "
    "READY = current authoritative evidence verifies the state. "
    "UNKNOWN = evidence is insufficient and no safe current probe is available."
)


def correct_row(row: dict) -> dict:
    out = copy.deepcopy(row)
    out["query"] = CLASSIFICATION_PREFIX + "\n\n" + row["query"]
    tools = out.get("tools") or []
    if len(tools) != 1 or tools[0].get("name") != "route":
        raise ValueError("expected exactly one route tool")
    tools[0]["description"] = ROUTE_DESCRIPTION
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    src = pathlib.Path(args.source)
    out = pathlib.Path(args.output)
    rows = [json.loads(line) for line in src.read_text().splitlines() if line.strip()]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(correct_row(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows))
    print(json.dumps({"rows": len(rows), "output": str(out)}, sort_keys=True))


if __name__ == "__main__":
    main()
