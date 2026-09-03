from __future__ import annotations

import math


def canonical_decision_state(row: dict) -> dict:
    applicability = row.get("applicability")
    decision = row.get("expected_decision")
    if applicability == "none" and decision is None:
        return {
            "applicability": "NONE",
            "decision": "NO_CALL",
            "tool_need": "unnecessary",
            "evidence_state": "sufficient",
            "cost_class": "low",
            "risk_class": "low",
        }
    if applicability == "route" and decision in {"PROBE", "READY", "UNKNOWN"}:
        return {
            "applicability": "ROUTE",
            "decision": decision,
            "tool_need": "required",
            "evidence_state": "sufficient" if decision == "READY" else "insufficient",
            "cost_class": "low",
            "risk_class": "low",
        }
    raise ValueError("invalid Stage C semantic row")


def _allocate(ids: list[str], weights: dict[str, float], budget: int) -> dict[str, int]:
    if budget < 0:
        raise ValueError("negative budget")
    if not ids:
        return {}
    total = sum(max(0.0, float(weights.get(case_id, 0.0))) for case_id in ids)
    if total <= 0:
        weights = {case_id: 1.0 for case_id in ids}
        total = float(len(ids))
    quotas = {case_id: max(0.0, float(weights.get(case_id, 0.0))) / total * budget for case_id in ids}
    counts = {case_id: math.floor(quotas[case_id]) for case_id in ids}
    remaining = budget - sum(counts.values())
    order = sorted(ids, key=lambda case_id: (-(quotas[case_id] - counts[case_id]), case_id))
    for case_id in order[:remaining]:
        counts[case_id] += 1
    return counts


def _materialize(rows_by_id: dict[str, dict], positives: list[str], negative_counts: dict[str, int]) -> list[dict]:
    out=[]
    for case_id in sorted(positives):
        row=rows_by_id[case_id]
        out.append({"case_id":case_id,"query":row["query"],"canonical_state":canonical_decision_state(row)})
    for case_id in sorted(negative_counts):
        row=rows_by_id[case_id]
        for occurrence in range(negative_counts[case_id]):
            out.append({"case_id":case_id,"query":row["query"],"canonical_state":canonical_decision_state(row),"sample_ordinal":occurrence})
    return out


def build_stage_c_arms(semantic_rows: list[dict], recovery_state: list[dict], additional_negative_budget: int) -> dict[str, list[dict]]:
    if any(row.get("split") != "train" for row in semantic_rows):
        raise ValueError("heldout rows are forbidden from Stage C training projection")
    rows_by_id={row["case_id"]:row for row in semantic_rows}
    positives=sorted(row["case_id"] for row in semantic_rows if row.get("applicability")=="route")
    negatives=sorted(row["case_id"] for row in semantic_rows if row.get("applicability")=="none" and row.get("expected_decision") is None)
    recovery_by_id={row["case_id"]:float(row["recovery_priority"]) for row in recovery_state}
    unknown=set(recovery_by_id)-set(negatives)
    if unknown:
        raise ValueError(f"recovery state references non-training-negative cases: {sorted(unknown)}")
    uniform={case_id:1.0 for case_id in negatives}
    adaptive={case_id:max(0.0,recovery_by_id.get(case_id,0.0)) for case_id in negatives}
    if sum(adaptive.values()) <= 0:
        adaptive=uniform
    a_extra=_allocate(negatives,uniform,additional_negative_budget)
    b_extra=_allocate(negatives,adaptive,additional_negative_budget)
    a_counts={case_id:1+a_extra.get(case_id,0) for case_id in negatives}
    b_counts={case_id:1+b_extra.get(case_id,0) for case_id in negatives}
    return {
        "A":_materialize(rows_by_id,positives,a_counts),
        "B":_materialize(rows_by_id,positives,b_counts),
    }

import hashlib
import json


def _jsonl_bytes(rows: list[dict]) -> bytes:
    return b"".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n" for row in rows)


def _stable_json_bytes(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def _behavioral_projection(row: dict, schema: dict, prefix: str) -> dict:
    state=row["canonical_state"]
    if state["applicability"] == "NONE":
        return {"query": row["query"], "tools": [schema], "answers": []}
    decision=state["decision"]
    if decision not in {"PROBE","READY","UNKNOWN"}:
        raise ValueError("invalid route decision")
    return {
        "query": prefix + row["query"],
        "tools": [schema],
        "answers": [{"name":"route","arguments":{"decision":decision}}],
    }


def build_outputs(semantic_rows: list[dict], recovery_state: list[dict], additional_negative_budget: int, schema: dict, prefix: str) -> dict:
    arms=build_stage_c_arms(semantic_rows,recovery_state,additional_negative_budget)
    files={}
    for arm in ("A","B"):
        slug=arm.lower()
        files[f"state/arm-{slug}.canonical.jsonl"]=_jsonl_bytes(arms[arm])
        files[f"data/arm-{slug}.train.needle.jsonl"]=_jsonl_bytes([
            _behavioral_projection(row,schema,prefix) for row in arms[arm]
        ])
    bindings=[]
    for path in sorted(files):
        payload=files[path]
        bindings.append({"path":path,"sha256":hashlib.sha256(payload).hexdigest(),"bytes":len(payload)})
    manifest={
        "schema_version":"needle-stage-c-dataset-manifest-v1",
        "additional_negative_budget_per_arm":additional_negative_budget,
        "arm_rows":{arm:len(arms[arm]) for arm in ("A","B")},
        "bindings":bindings,
    }
    files["manifests/stage-c-dataset-manifest.json"]=_stable_json_bytes(manifest)
    return {"arms":arms,"files":files}
