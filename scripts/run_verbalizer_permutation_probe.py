#!/usr/bin/env python3
import argparse
import json
import pathlib
import time

DECISIONS = ("PROBE", "READY", "UNKNOWN")
LABELS = ["A", "B", "C"]
PREFIX = "Use route to classify the following evidence:\n\n"
SEMANTICS = {
    "PROBE": "current verification is needed and safely possible.",
    "READY": "current authoritative evidence verifies the state.",
    "UNKNOWN": "evidence is insufficient and no safe current probe is available.",
}


def permutation_specs() -> dict[str, dict]:
    return {
        "P1": {"labels": LABELS.copy(), "to_decision": {"A": "PROBE", "B": "READY", "C": "UNKNOWN"}},
        "P2": {"labels": LABELS.copy(), "to_decision": {"A": "PROBE", "B": "UNKNOWN", "C": "READY"}},
        "P3": {"labels": LABELS.copy(), "to_decision": {"A": "READY", "B": "PROBE", "C": "UNKNOWN"}},
        "P4": {"labels": LABELS.copy(), "to_decision": {"A": "READY", "B": "UNKNOWN", "C": "PROBE"}},
        "P5": {"labels": LABELS.copy(), "to_decision": {"A": "UNKNOWN", "B": "PROBE", "C": "READY"}},
        "P6": {"labels": LABELS.copy(), "to_decision": {"A": "UNKNOWN", "B": "READY", "C": "PROBE"}},
    }


def _description(mapping_name: str) -> str:
    mapping = permutation_specs()[mapping_name]["to_decision"]
    pieces = []
    for label in LABELS:
        decision = mapping[label]
        pieces.append(f"{label} = {decision}: {SEMANTICS[decision]}")
    return "Classify the current evidence state. Always use route for this classification. " + " ".join(pieces)


def route_schema(mapping_name: str) -> dict:
    return {
        "name": "route",
        "parameters": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": LABELS.copy()},
            },
            "required": ["decision"],
        },
        "description": _description(mapping_name),
    }


def serialize_schema(schema: dict) -> str:
    return json.dumps(schema, ensure_ascii=False, separators=(",", ":"))


def frame_query(query: str) -> str:
    return PREFIX + query


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
        rows.append({"id": f"train-{index:03d}", "query": raw["query"], "expected": decision})
    return rows


def _classify_call(response: dict) -> tuple[str, bool]:
    calls = response.get("function_calls") or []
    if response.get("type") != "call" or not calls:
        return "NO_CALL", False
    if len(calls) != 1 or calls[0].get("name") != "route":
        return "INVALID", False
    value = (calls[0].get("arguments") or {}).get("decision")
    if value not in LABELS:
        return "INVALID", False
    return value, True


def evaluate(cases: list[dict], mapping_name: str, max_new_tokens: int) -> list[dict]:
    import needle

    spec = permutation_specs()[mapping_name]
    mapping = spec["to_decision"]
    schema = route_schema(mapping_name)
    schema_json = serialize_schema(schema)
    agent = needle.Needle(tools=[schema])
    records = []
    for case in cases:
        agent.reset()
        query = frame_query(case["query"])
        started = time.perf_counter()
        response = agent.complete(query, max_new_tokens=max_new_tokens)
        latency_ms = (time.perf_counter() - started) * 1000.0
        raw_label, valid = _classify_call(response)
        predicted = mapping.get(raw_label, raw_label)
        records.append({
            "id": case["id"],
            "mapping_name": mapping_name,
            "mapping": mapping,
            "source_query": case["query"],
            "framed_query": query,
            "schema_json": schema_json,
            "expected": case["expected"],
            "predicted_token": raw_label,
            "predicted": predicted,
            "valid_structured_call": valid,
            "correct": predicted == case["expected"],
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
    parser.add_argument("--mapping", choices=list(permutation_specs()), required=True)
    parser.add_argument("--training-jsonl", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    args = parser.parse_args()

    rows = evaluate(
        load_training_cases(pathlib.Path(args.training_jsonl)),
        mapping_name=args.mapping,
        max_new_tokens=args.max_new_tokens,
    )
    write_jsonl(pathlib.Path(args.output), rows)


if __name__ == "__main__":
    main()
