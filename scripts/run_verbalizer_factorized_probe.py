#!/usr/bin/env python3
import argparse
import json
import pathlib
import time

DECISIONS = ("PROBE", "READY", "UNKNOWN")
PREFIX = "Use route to classify the following evidence:\n\n"
SEMANTICS = {
    "PROBE": "current verification is needed and safely possible.",
    "READY": "current authoritative evidence verifies the state.",
    "UNKNOWN": "evidence is insufficient and no safe current probe is available.",
}


def flat_specs() -> dict[str, dict]:
    return {
        "A": {
            "labels": ["PROBE", "READY", "UNKNOWN"],
            "to_decision": {"PROBE": "PROBE", "READY": "READY", "UNKNOWN": "UNKNOWN"},
        },
        "B": {
            "labels": ["probe", "ready", "unknown"],
            "to_decision": {"probe": "PROBE", "ready": "READY", "unknown": "UNKNOWN"},
        },
        "C": {
            "labels": ["A", "B", "C"],
            "to_decision": {"A": "PROBE", "B": "READY", "C": "UNKNOWN"},
        },
    }


def _flat_description(arm: str) -> str:
    spec = flat_specs()[arm]
    if arm == "A":
        return (
            "Classify the current evidence state. Always use route for this classification. "
            "PROBE = current verification is needed and safely possible. "
            "READY = current authoritative evidence verifies the state. "
            "UNKNOWN = evidence is insufficient and no safe current probe is available."
        )
    pieces = []
    for label in spec["labels"]:
        decision = spec["to_decision"][label]
        pieces.append(f"{label} = {decision}: {SEMANTICS[decision]}")
    return "Classify the current evidence state. Always use route for this classification. " + " ".join(pieces)


def flat_schema(arm: str) -> dict:
    spec = flat_specs()[arm]
    return {
        "name": "route",
        "parameters": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": list(spec["labels"])},
            },
            "required": ["decision"],
        },
        "description": _flat_description(arm),
    }


def evidence_schema() -> dict:
    return {
        "name": "route",
        "parameters": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["verified", "insufficient"]},
            },
            "required": ["decision"],
        },
        "description": (
            "Classify current evidence. verified = current authoritative evidence verifies the state. "
            "insufficient = current evidence does not currently verify the state."
        ),
    }


def probe_schema() -> dict:
    return {
        "name": "route",
        "parameters": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["available", "unavailable"]},
            },
            "required": ["decision"],
        },
        "description": (
            "Classify safe current probe availability. available = a safe current distinguishing probe can be run now. "
            "unavailable = no safe current authoritative probe is currently available."
        ),
    }


def serialize_schema(schema: dict) -> str:
    return json.dumps(schema, ensure_ascii=False, separators=(",", ":"))


def frame_query(query: str) -> str:
    return PREFIX + query


def evidence_query(query: str) -> str:
    return "Classify current evidence as verified or insufficient. Use route.\n\n" + query


def probe_query(query: str) -> str:
    return (
        "Current evidence is insufficient. Classify whether a safe current distinguishing probe is available or unavailable. "
        "Use route.\n\n" + query
    )


def expected_factorized(decision: str) -> tuple[str, str | None]:
    if decision == "READY":
        return "verified", None
    if decision == "PROBE":
        return "insufficient", "available"
    if decision == "UNKNOWN":
        return "insufficient", "unavailable"
    raise ValueError(f"unsupported decision: {decision!r}")


def factorized_final(evidence: str, probe: str | None) -> str:
    if evidence == "verified":
        return "READY"
    if evidence == "insufficient" and probe == "available":
        return "PROBE"
    if evidence == "insufficient" and probe == "unavailable":
        return "UNKNOWN"
    return "INVALID"


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


def _classify_call(response: dict, *, tool: str, field: str, allowed: set[str]) -> tuple[str, bool]:
    calls = response.get("function_calls") or []
    if response.get("type") != "call" or not calls:
        return "NO_CALL", False
    if len(calls) != 1 or calls[0].get("name") != tool:
        return "INVALID", False
    value = (calls[0].get("arguments") or {}).get(field)
    if value not in allowed:
        return "INVALID", False
    return value, True


def evaluate_flat(cases: list[dict], arm: str, max_new_tokens: int) -> list[dict]:
    import needle

    spec = flat_specs()[arm]
    schema = flat_schema(arm)
    schema_json = serialize_schema(schema)
    agent = needle.Needle(tools=[schema])
    records = []
    for case in cases:
        agent.reset()
        query = frame_query(case["query"])
        started = time.perf_counter()
        response = agent.complete(query, max_new_tokens=max_new_tokens)
        latency_ms = (time.perf_counter() - started) * 1000.0
        raw_label, valid = _classify_call(
            response,
            tool="route",
            field="decision",
            allowed=set(spec["labels"]),
        )
        predicted = spec["to_decision"].get(raw_label, raw_label)
        records.append({
            "id": case["id"],
            "arm": arm,
            "representation": {"A": "uppercase", "B": "lowercase", "C": "one_token_codes"}[arm],
            "source_query": case["query"],
            "framed_query": query,
            "schema_json": schema_json,
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


def evaluate_factorized(cases: list[dict], max_new_tokens: int) -> list[dict]:
    import needle

    stage1_schema = evidence_schema()
    stage2_schema = probe_schema()
    stage1_schema_json = serialize_schema(stage1_schema)
    stage2_schema_json = serialize_schema(stage2_schema)
    evidence_agent = needle.Needle(tools=[stage1_schema])
    probe_agent = needle.Needle(tools=[stage2_schema])
    records = []
    for case in cases:
        stage1_expected, stage2_expected = expected_factorized(case["expected"])
        evidence_agent.reset()
        q1 = evidence_query(case["query"])
        started = time.perf_counter()
        r1 = evidence_agent.complete(q1, max_new_tokens=max_new_tokens)
        stage1_ms = (time.perf_counter() - started) * 1000.0
        stage1_predicted, stage1_valid = _classify_call(
            r1,
            tool="route",
            field="decision",
            allowed={"verified", "insufficient"},
        )

        stage2_predicted = None
        stage2_valid = None
        r2 = None
        stage2_ms = 0.0
        q2 = probe_query(case["query"])
        if stage1_valid and stage1_predicted == "insufficient":
            probe_agent.reset()
            started = time.perf_counter()
            r2 = probe_agent.complete(q2, max_new_tokens=max_new_tokens)
            stage2_ms = (time.perf_counter() - started) * 1000.0
            stage2_predicted, stage2_valid = _classify_call(
                r2,
                tool="route",
                field="decision",
                allowed={"available", "unavailable"},
            )

        if not stage1_valid:
            predicted = stage1_predicted
            valid = False
        elif stage1_predicted == "verified":
            predicted = "READY"
            valid = True
        elif stage2_valid:
            predicted = factorized_final(stage1_predicted, stage2_predicted)
            valid = predicted in DECISIONS
        else:
            predicted = stage2_predicted or "NO_CALL"
            valid = False

        records.append({
            "id": case["id"],
            "arm": "D",
            "representation": "factorized_two_stage",
            "source_query": case["query"],
            "framed_query": q1,
            "expected": case["expected"],
            "predicted": predicted,
            "valid_structured_call": valid,
            "correct": predicted == case["expected"],
            "stage1_expected": stage1_expected,
            "stage1_predicted": stage1_predicted,
            "stage1_valid": stage1_valid,
            "stage1_schema_json": stage1_schema_json,
            "stage1_framed_query": q1,
            "stage1_raw_response": r1,
            "stage2_expected": stage2_expected,
            "stage2_predicted": stage2_predicted,
            "stage2_valid": stage2_valid,
            "stage2_schema_json": stage2_schema_json,
            "stage2_framed_query": q2,
            "stage2_raw_response": r2,
            "max_new_tokens": max_new_tokens,
            "latency_ms": round(stage1_ms + stage2_ms, 3),
        })
    return records


def write_jsonl(path: pathlib.Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True, choices=list("ABCD"))
    parser.add_argument("--training-jsonl", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    args = parser.parse_args()

    cases = load_training_cases(pathlib.Path(args.training_jsonl))
    records = (
        evaluate_flat(cases, args.arm, args.max_new_tokens)
        if args.arm in "ABC"
        else evaluate_factorized(cases, args.max_new_tokens)
    )
    write_jsonl(pathlib.Path(args.output), records)


if __name__ == "__main__":
    main()
