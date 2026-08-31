#!/usr/bin/env python3
import argparse
import json
import pathlib


def derive_row(row: dict) -> dict:
    derived = dict(row)
    derived.pop("reasoning", None)
    return derived


def main() -> None:
    parser = argparse.ArgumentParser(description="Derive a Needle JSONL dataset with reasoning supervision removed.")
    parser.add_argument("source")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source = pathlib.Path(args.source)
    output = pathlib.Path(args.output)
    rows = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
    derived = [derive_row(row) for row in rows]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in derived))
    print(json.dumps({"rows": len(derived), "reasoning_removed": sum("reasoning" in row for row in rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
