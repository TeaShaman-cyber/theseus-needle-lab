#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import time

DECISIONS = {"PROBE", "READY", "UNKNOWN"}


def _load_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _expected_from_projection(row: dict) -> str:
    answers = row.get("answers") or []
    if not answers:
        return "NO_CALL"
    if len(answers) != 1 or answers[0].get("name") != "route":
        raise ValueError("unsupported projection answer shape")
    decision = (answers[0].get("arguments") or {}).get("decision")
    if decision not in DECISIONS:
        raise ValueError("invalid projection decision")
    return decision


def load_bound_cases(projection_path: pathlib.Path, semantic_path: pathlib.Path, split: str) -> list[dict]:
    projected = _load_jsonl(projection_path)
    semantic = [row for row in _load_jsonl(semantic_path) if row.get("split") == split]
    if len(projected) != len(semantic):
        raise ValueError("projection/semantic row count mismatch")
    rows = []
    for projection, source in zip(projected, semantic):
        expected = _expected_from_projection(projection)
        source_expected = source.get("expected_decision") if source.get("applicability") == "route" else "NO_CALL"
        if expected != source_expected:
            raise ValueError("projection/semantic expected mismatch")
        if source.get("applicability") == "route":
            if not projection.get("query", "").endswith(source["query"]):
                raise ValueError("projection/semantic query mismatch")
            category = f"{split}_positive"
        else:
            if projection.get("query") != source["query"]:
                raise ValueError("projection/semantic query mismatch")
            category = f"{split}_negative"
        rows.append({
            "id": source["case_id"],
            "family_id": source["family_id"],
            "category": category,
            "query": projection["query"],
            "tools": projection["tools"],
            "expected": expected,
        })
    return rows


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


def evaluate(cases: list[dict], *, weights: str | None, model_id: str, max_new_tokens: int) -> list[dict]:
    import needle

    records = []
    for case in cases:
        # Construct from the exact embedded schema in the committed projection.
        agent = needle.Needle(tools=case["tools"], weights=weights)
        started = time.perf_counter()
        response = agent.complete(case["query"], max_new_tokens=max_new_tokens)
        latency_ms = (time.perf_counter() - started) * 1000.0
        predicted = classify_response(response)
        records.append({
            "id": case["id"],
            "family_id": case["family_id"],
            "category": case["category"],
            "expected": case["expected"],
            "predicted": predicted,
            "correct": predicted == case["expected"],
            "model_id": model_id,
            "max_new_tokens": max_new_tokens,
            "latency_ms": round(latency_ms, 3),
            "raw_response": response,
        })
    return records


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--projection", type=pathlib.Path, required=True)
    p.add_argument("--semantic", type=pathlib.Path, required=True)
    p.add_argument("--split", choices=["train", "heldout"], required=True)
    p.add_argument("--weights")
    p.add_argument("--model-id", required=True)
    p.add_argument("--max-new-tokens", type=int, default=256)
    p.add_argument("--output", type=pathlib.Path, required=True)
    args = p.parse_args()
    cases = load_bound_cases(args.projection, args.semantic, args.split)
    rows = evaluate(cases, weights=args.weights, model_id=args.model_id, max_new_tokens=args.max_new_tokens)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


if __name__ == "__main__":
    main()
