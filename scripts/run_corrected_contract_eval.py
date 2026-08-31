#!/usr/bin/env python3
import argparse
import json
import pathlib
import time

DECISIONS = {"PROBE", "READY", "UNKNOWN"}
CLASSIFICATION_PREFIX = "Use route to classify the following evidence:"
ROUTE_DESCRIPTION = (
    "Classify the current evidence state. Always use route for this classification. "
    "PROBE = current verification is needed and safely possible. "
    "READY = current authoritative evidence verifies the state. "
    "UNKNOWN = evidence is insufficient and no safe current probe is available."
)
ROUTE_SCHEMA = {
    "name": "route",
    "description": ROUTE_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["PROBE", "READY", "UNKNOWN"]}
        },
        "required": ["decision"],
    },
}


def frame_query(query: str) -> str:
    return CLASSIFICATION_PREFIX + "\n\n" + query


def classify_response(response: dict) -> str:
    calls = response.get("function_calls") or []
    if response.get("type") != "call" or not calls:
        return "NO_CALL"
    if len(calls) != 1:
        return "INVALID"
    call = calls[0]
    if call.get("name") != "route":
        return "INVALID"
    decision = (call.get("arguments") or {}).get("decision")
    return decision if decision in DECISIONS else "INVALID"


def load_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_training_cases(path: pathlib.Path) -> list[dict]:
    out = []
    for index, row in enumerate(load_jsonl(path), start=1):
        answers = row.get("answers") or []
        if len(answers) != 1 or answers[0].get("name") != "route":
            raise ValueError(f"unsupported training answer shape at row {index}")
        expected = (answers[0].get("arguments") or {}).get("decision")
        if expected not in DECISIONS:
            raise ValueError(f"invalid training decision at row {index}: {expected!r}")
        out.append({"id": f"train-{index:03d}", "category": "training_replay", "query": row["query"], "expected": expected})
    return out


def load_cases(path: pathlib.Path) -> list[dict]:
    return load_jsonl(path)


def evaluate(cases: list[dict], weights: str | None, model_id: str, max_new_tokens: int) -> list[dict]:
    import needle
    agent = needle.Needle(tools=[ROUTE_SCHEMA], weights=weights)
    records = []
    for case in cases:
        agent.reset()
        query = frame_query(case["query"])
        started = time.perf_counter()
        response = agent.complete(query, max_new_tokens=max_new_tokens)
        latency_ms = (time.perf_counter() - started) * 1000.0
        predicted = classify_response(response)
        records.append({
            "id": case["id"],
            "category": case["category"],
            "query": case["query"],
            "framed_query": query,
            "expected": case["expected"],
            "predicted": predicted,
            "valid_route_call": predicted in DECISIONS,
            "correct": predicted == case["expected"],
            "confidence": response.get("confidence"),
            "latency_ms": round(latency_ms, 3),
            "model_id": model_id,
            "max_new_tokens": max_new_tokens,
            "raw_response": response,
        })
    return records


def main() -> None:
    p = argparse.ArgumentParser()
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--training-jsonl")
    src.add_argument("--cases")
    p.add_argument("--output", required=True)
    p.add_argument("--model-id", required=True)
    p.add_argument("--weights")
    p.add_argument("--max-new-tokens", type=int, default=256)
    args = p.parse_args()
    cases = load_training_cases(pathlib.Path(args.training_jsonl)) if args.training_jsonl else load_cases(pathlib.Path(args.cases))
    records = evaluate(cases, args.weights, args.model_id, args.max_new_tokens)
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records))


if __name__ == "__main__":
    main()
