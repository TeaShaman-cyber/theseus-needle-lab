#!/usr/bin/env python3
import argparse
import importlib.util
import json
import pathlib
import time

_PREDECESSOR_PATH = pathlib.Path(__file__).with_name("run_verbalizer_factorized_probe.py")
_spec = importlib.util.spec_from_file_location("needle_verbalizer_predecessor", _PREDECESSOR_PATH)
_predecessor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_predecessor)

DECISIONS = _predecessor.DECISIONS
PREFIX = _predecessor.PREFIX
SEMANTICS = _predecessor.SEMANTICS
serialize_schema = _predecessor.serialize_schema
frame_query = _predecessor.frame_query
load_training_cases = _predecessor.load_training_cases


def arm_specs() -> dict[str, dict]:
    prior = _predecessor.flat_specs()
    return {
        "A": {
            "labels": list(prior["A"]["labels"]),
            "to_decision": dict(prior["A"]["to_decision"]),
        },
        "B": {
            "labels": list(prior["B"]["labels"]),
            "to_decision": dict(prior["B"]["to_decision"]),
        },
        "C": {
            "labels": ["check", "ready", "unknown"],
            "to_decision": {"check": "PROBE", "ready": "READY", "unknown": "UNKNOWN"},
        },
    }


def _description(arm: str) -> str:
    if arm in "AB":
        return _predecessor.flat_schema(arm)["description"]
    spec = arm_specs()[arm]
    pieces = []
    for label in spec["labels"]:
        decision = spec["to_decision"][label]
        pieces.append(f"{label} = {decision}: {SEMANTICS[decision]}")
    return "Classify the current evidence state. Always use route for this classification. " + " ".join(pieces)


def route_schema(arm: str) -> dict:
    if arm in "AB":
        return _predecessor.flat_schema(arm)
    spec = arm_specs()[arm]
    return {
        "name": "route",
        "parameters": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": list(spec["labels"])},
            },
            "required": ["decision"],
        },
        "description": _description(arm),
    }


def _encode_pieces(tokenizer, text: str) -> list[str]:
    if hasattr(tokenizer, "sp"):
        return list(tokenizer.sp.EncodeAsPieces(text))
    try:
        return list(tokenizer.encode(text, out_type=str))
    except TypeError:
        return list(tokenizer.EncodeAsPieces(text))


def tokenize_labels(tokenizer, labels: list[str]) -> dict[str, dict]:
    out = {}
    for label in labels:
        context = json.dumps({"decision": label}, ensure_ascii=False, separators=(",", ":"))
        out[label] = {
            "json_value_context": context,
            "pieces": _encode_pieces(tokenizer, context),
        }
    return out


def _classify_call(response: dict, allowed: set[str]) -> tuple[str, bool]:
    calls = response.get("function_calls") or []
    if response.get("type") != "call" or not calls:
        return "NO_CALL", False
    if len(calls) != 1 or calls[0].get("name") != "route":
        return "INVALID", False
    value = (calls[0].get("arguments") or {}).get("decision")
    if value not in allowed:
        return "INVALID", False
    return value, True


def evaluate(cases: list[dict], arm: str, max_new_tokens: int) -> list[dict]:
    import needle
    from needle.model.tokenizer import get_tokenizer

    spec = arm_specs()[arm]
    schema = route_schema(arm)
    schema_json = serialize_schema(schema)
    tokenizer = get_tokenizer()
    label_tokenization = tokenize_labels(tokenizer, spec["labels"])
    agent = needle.Needle(tools=[schema])
    records = []
    for case in cases:
        agent.reset()
        query = frame_query(case["query"])
        started = time.perf_counter()
        response = agent.complete(query, max_new_tokens=max_new_tokens)
        latency_ms = (time.perf_counter() - started) * 1000.0
        raw_label, valid = _classify_call(response, set(spec["labels"]))
        predicted = spec["to_decision"].get(raw_label, raw_label)
        records.append({
            "id": case["id"],
            "arm": arm,
            "representation": {"A": "uppercase", "B": "lowercase", "C": "semantic_check"}[arm],
            "source_query": case["query"],
            "framed_query": query,
            "schema_json": schema_json,
            "label_tokenization": label_tokenization,
            "expected": case["expected"],
            "predicted_label": raw_label,
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
    parser.add_argument("--arm", required=True, choices=list("ABC"))
    parser.add_argument("--training-jsonl", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    args = parser.parse_args()
    cases = load_training_cases(pathlib.Path(args.training_jsonl))
    write_jsonl(pathlib.Path(args.output), evaluate(cases, args.arm, args.max_new_tokens))


if __name__ == "__main__":
    main()
