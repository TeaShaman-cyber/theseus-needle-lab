#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import time

try:
    from scripts.build_stage_c_dataset import POLICY_STATE_SCHEMA, canonical_decision_state
except ModuleNotFoundError:
    from build_stage_c_dataset import POLICY_STATE_SCHEMA, canonical_decision_state

DECISIONS={"PROBE","READY","UNKNOWN"}
STATE_KEYS=("applicability","decision","tool_need","evidence_state","cost_class","risk_class")


def _strict_state(arguments):
    if not isinstance(arguments,dict) or set(arguments) != set(STATE_KEYS):
        return "INVALID"
    state={k:arguments[k] for k in STATE_KEYS}
    if state["applicability"] not in {"NONE","ROUTE"}:
        return "INVALID"
    if state["decision"] not in {"NO_CALL","PROBE","READY","UNKNOWN"}:
        return "INVALID"
    if state["applicability"]=="NONE" and state["decision"]!="NO_CALL":
        return "INVALID"
    if state["applicability"]=="ROUTE" and state["decision"] not in DECISIONS:
        return "INVALID"
    if state["tool_need"] not in {"unnecessary","required","helpful","unknown"}:
        return "INVALID"
    if state["evidence_state"] not in {"sufficient","insufficient","conflicting"}:
        return "INVALID"
    if state["cost_class"] not in {"low","medium","high"} or state["risk_class"] not in {"low","medium","high"}:
        return "INVALID"
    return state


def classify_stage_c_response(response: dict, *, factorized: bool) -> dict:
    calls=response.get("function_calls") or []
    if response.get("type") != "call" or not calls:
        return {"predicted_route":"NO_CALL","predicted_state":"INVALID" if factorized else None}
    route_calls=[c for c in calls if c.get("name")=="route"]
    other=[c for c in calls if c.get("name") not in ({"route","policy_state"} if factorized else {"route"})]
    if other or len(route_calls)>1:
        predicted_route="INVALID"
    elif not route_calls:
        predicted_route="NO_CALL"
    else:
        decision=(route_calls[0].get("arguments") or {}).get("decision")
        predicted_route=decision if decision in DECISIONS else "INVALID"
    if not factorized:
        if len(calls)!=len(route_calls):
            predicted_route="INVALID"
        return {"predicted_route":predicted_route,"predicted_state":None}
    state_calls=[c for c in calls if c.get("name")=="policy_state"]
    predicted_state=_strict_state(state_calls[0].get("arguments")) if len(state_calls)==1 else "INVALID"
    return {"predicted_route":predicted_route,"predicted_state":predicted_state}


def build_stage_c_case(source: dict, route_schema: dict, prefix: str, arm_id: str) -> dict:
    if arm_id not in {"A","B"}:
        raise ValueError("invalid arm_id")
    factorized=arm_id=="B"
    state=canonical_decision_state(source)
    expected_route=state["decision"] if state["applicability"]=="ROUTE" else "NO_CALL"
    query=prefix+source["query"] if state["applicability"]=="ROUTE" else source["query"]
    return {
        "id":source["case_id"],
        "family_id":source["family_id"],
        "category":f"{source['split']}_{'positive' if state['applicability']=='ROUTE' else 'negative'}",
        "query":query,
        "tools":[POLICY_STATE_SCHEMA,route_schema] if factorized else [route_schema],
        "expected_route":expected_route,
        "expected_state":state if factorized else None,
        "factorized":factorized,
    }


def evaluate(cases: list[dict], *, weights: str, model_id: str, max_new_tokens: int) -> list[dict]:
    import needle
    rows=[]
    for case in cases:
        agent=needle.Needle(tools=case["tools"],weights=weights)
        started=time.perf_counter()
        response=agent.complete(case["query"],max_new_tokens=max_new_tokens)
        latency_ms=(time.perf_counter()-started)*1000.0
        parsed=classify_stage_c_response(response,factorized=case["factorized"])
        state_correct=(parsed["predicted_state"]==case["expected_state"]) if case["factorized"] else None
        rows.append({
            "id":case["id"],"family_id":case["family_id"],"category":case["category"],
            "expected":case["expected_route"],"predicted":parsed["predicted_route"],
            "correct":parsed["predicted_route"]==case["expected_route"],
            "expected_state":case["expected_state"],"predicted_state":parsed["predicted_state"],"state_correct":state_correct,
            "model_id":model_id,"max_new_tokens":max_new_tokens,"latency_ms":round(latency_ms,3),"raw_response":response,
        })
    return rows


def _load_jsonl(path):
    return [json.loads(x) for x in pathlib.Path(path).read_text(encoding='utf-8').splitlines() if x.strip()]


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--semantic',type=pathlib.Path,required=True)
    p.add_argument('--route-schema',type=pathlib.Path,required=True)
    p.add_argument('--prefix',type=pathlib.Path,required=True)
    p.add_argument('--split',choices=['train','heldout'],required=True)
    p.add_argument('--arm-id',choices=['A','B'],required=True)
    p.add_argument('--weights',required=True)
    p.add_argument('--model-id',required=True)
    p.add_argument('--max-new-tokens',type=int,default=256)
    p.add_argument('--output',type=pathlib.Path,required=True)
    a=p.parse_args()
    semantic=[r for r in _load_jsonl(a.semantic) if r.get('split')==a.split]
    schema=json.loads(a.route_schema.read_text(encoding='utf-8'))
    prefix=a.prefix.read_text(encoding='utf-8')
    cases=[build_stage_c_case(r,schema,prefix,a.arm_id) for r in semantic]
    rows=evaluate(cases,weights=a.weights,model_id=a.model_id,max_new_tokens=a.max_new_tokens)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows),encoding='utf-8')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
