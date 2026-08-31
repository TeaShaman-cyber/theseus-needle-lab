#!/usr/bin/env python3
import argparse
import json
import pathlib
import time

DECISIONS = ("PROBE", "READY", "UNKNOWN")
DESCRIPTION = (
    "Classify the current evidence state. Always use route for this classification. "
    "PROBE = current verification is needed and safely possible. "
    "READY = current authoritative evidence verifies the state. "
    "UNKNOWN = evidence is insufficient and no safe current probe is available."
)
PREFIX = "Use route to classify the following evidence:\n\n"


def arm_specs() -> dict[str, dict[str, bool]]:
    return {
        "A": {"described_schema": False, "explicit_prefix": False},
        "B": {"described_schema": False, "explicit_prefix": True},
        "C": {"described_schema": True, "explicit_prefix": False},
        "D": {"described_schema": True, "explicit_prefix": True},
    }


def route_schema(described: bool) -> dict:
    schema = {
        "name": "route",
        "parameters": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": list(DECISIONS)},
            },
            "required": ["decision"],
        },
    }
    if described:
        schema["description"] = DESCRIPTION
    return schema


def frame_query(query: str, explicit_prefix: bool) -> str:
    return PREFIX + query if explicit_prefix else query


def canary_cases() -> list[dict]:
    return [
        {"id": f"canary-{decision}", "query": f"Call route with decision {decision}.", "expected": decision}
        for decision in DECISIONS
    ]


def load_training_cases(path: pathlib.Path) -> list[dict]:
    rows = []
    for index, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        raw = json.loads(line)
        answers = raw.get("answers") or []
        if len(answers) != 1 or answers[0].get("name") != "route":
            raise ValueError(f"row {index} is not a single route-call positive example")
        decision = (answers[0].get("arguments") or {}).get("decision")
        if decision not in DECISIONS:
            raise ValueError(f"invalid decision at row {index}: {decision!r}")
        rows.append({
            "id": f"train-{index:03d}",
            "query": raw["query"],
            "expected": decision,
        })
    return rows


def classify_response(response: dict) -> tuple[str, bool]:
    calls = response.get("function_calls") or []
    if response.get("type") != "call" or not calls:
        return "NO_CALL", False
    if len(calls) != 1:
        return "INVALID", False
    call = calls[0]
    if call.get("name") != "route":
        return "INVALID", False
    decision = (call.get("arguments") or {}).get("decision")
    if decision not in DECISIONS:
        return "INVALID", False
    return decision, True


def evaluate(cases: list[dict], *, described_schema: bool, explicit_prefix: bool,
             max_new_tokens: int, condition: str) -> list[dict]:
    import needle

    agent = needle.Needle(tools=[route_schema(described_schema)])
    records = []
    for case in cases:
        agent.reset()
        query = frame_query(case["query"], explicit_prefix)
        started = time.perf_counter()
        response = agent.complete(query, max_new_tokens=max_new_tokens)
        latency_ms = (time.perf_counter() - started) * 1000.0
        predicted, valid = classify_response(response)
        records.append({
            "id": case["id"],
            "condition": condition,
            "source_query": case["query"],
            "query": query,
            "expected": case["expected"],
            "predicted": predicted,
            "valid_route_call": valid,
            "correct": predicted == case["expected"],
            "described_schema": described_schema,
            "explicit_prefix": explicit_prefix,
            "max_new_tokens": max_new_tokens,
            "latency_ms": round(latency_ms, 3),
            "raw_response": response,
        })
    return records


def write_jsonl(path: pathlib.Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records))


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--canaries", action="store_true")
    group.add_argument("--arm", choices=sorted(arm_specs()))
    parser.add_argument("--training-jsonl")
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    args = parser.parse_args()

    if args.canaries:
        cases = canary_cases()
        spec = {"described_schema": False, "explicit_prefix": False}
        condition = "canaries"
    else:
        if not args.training_jsonl:
            parser.error("--training-jsonl is required with --arm")
        cases = load_training_cases(pathlib.Path(args.training_jsonl))
        spec = arm_specs()[args.arm]
        condition = args.arm

    records = evaluate(
        cases,
        described_schema=spec["described_schema"],
        explicit_prefix=spec["explicit_prefix"],
        max_new_tokens=args.max_new_tokens,
        condition=condition,
    )
    write_jsonl(pathlib.Path(args.output), records)


if __name__ == "__main__":
    main()
