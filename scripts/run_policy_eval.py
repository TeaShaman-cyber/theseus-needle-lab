#!/usr/bin/env python3
import argparse
import json
import pathlib
import time

DECISIONS = {"PROBE", "READY", "UNKNOWN"}
ROUTE_SCHEMA = {
    "name": "route",
    "parameters": {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["PROBE", "READY", "UNKNOWN"]}
        },
        "required": ["decision"],
    },
}


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


def load_cases(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_training_cases(path: pathlib.Path) -> list[dict]:
    rows = []
    for index, raw in enumerate(load_cases(path), start=1):
        answers = raw.get("answers") or []
        if not answers:
            expected = "NO_CALL"
        elif len(answers) == 1 and answers[0].get("name") == "route":
            expected = (answers[0].get("arguments") or {}).get("decision")
            if expected not in DECISIONS:
                raise ValueError(f"invalid training decision at row {index}: {expected!r}")
        else:
            raise ValueError(f"unsupported training answer shape at row {index}")
        rows.append({
            "id": f"train-{index:03d}",
            "category": "training_replay",
            "query": raw["query"],
            "expected": expected,
        })
    return rows


def evaluate(cases: list[dict], weights: str | None, model_id: str, max_new_tokens: int) -> list[dict]:
    import needle

    agent = needle.Needle(tools=[ROUTE_SCHEMA], weights=weights)
    records = []
    for case in cases:
        agent.reset()
        started = time.perf_counter()
        response = agent.complete(case["query"], max_new_tokens=max_new_tokens)
        latency_ms = (time.perf_counter() - started) * 1000.0
        predicted = classify_response(response)
        records.append({
            "id": case["id"],
            "category": case["category"],
            "query": case["query"],
            "expected": case["expected"],
            "predicted": predicted,
            "correct": predicted == case["expected"],
            "confidence": response.get("confidence"),
            "latency_ms": round(latency_ms, 3),
            "model_id": model_id,
            "max_new_tokens": max_new_tokens,
            "raw_response": response,
        })
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--cases")
    source.add_argument("--training-jsonl")
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--weights")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    args = parser.parse_args()

    cases = load_training_cases(pathlib.Path(args.training_jsonl)) if args.training_jsonl else load_cases(pathlib.Path(args.cases))
    records = evaluate(
        cases,
        args.weights,
        args.model_id,
        args.max_new_tokens,
    )
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records))


if __name__ == "__main__":
    main()
