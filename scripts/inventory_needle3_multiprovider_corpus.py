from __future__ import annotations
import argparse, collections, hashlib, json, pathlib, sqlite3
from dataclasses import dataclass

SCHEMA = "theseus.needle3.multiprovider_corpus_inventory.v1"
REQUIRED_TABLES = {"artifacts","corpus_meta","message_sources","messages","payload_pages","sessions"}

@dataclass(frozen=True)
class SourceSpec:
    name: str
    path: pathlib.Path
    adapter: str | None

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def parse_mapping(values,label):
    out={}
    for value in values:
        if "=" not in value:
            raise ValueError(f"{label} must use NAME=VALUE: {value!r}")
        k,v=value.split("=",1)
        k=k.strip(); v=v.strip()
        if not k or not v:
            raise ValueError(f"{label} must use non-empty NAME=VALUE")
        if k in out:
            raise ValueError(f"duplicate {label} name: {k}")
        out[k]=v
    return out

def validate_schema(conn):
    tables={r[0] for r in conn.execute("select name from sqlite_master where type='table' or type='view'")}
    missing=sorted(REQUIRED_TABLES-tables)
    if missing:
        raise ValueError(f"missing required corpus tables: {missing}")
    row=conn.execute("select value from corpus_meta where key='schema_version'").fetchone()
    if row is None:
        raise ValueError("missing corpus schema_version")
    return str(row[0])

def selected_rows(conn,adapter):
    if adapter is None:
        q="""select m.row_id,m.session_id,m.ordinal,m.canonical_message_sha256,m.role,m.content_type,m.search_class
             from messages m order by m.session_id,m.ordinal,m.row_id"""
        return list(conn.execute(q))
    q="""select distinct m.row_id,m.session_id,m.ordinal,m.canonical_message_sha256,m.role,m.content_type,m.search_class
         from messages m
         join message_sources ms on ms.message_row_id=m.row_id
         join payload_pages pp on pp.page_id=ms.page_id
         join artifacts a on a.artifact_id=pp.artifact_id
         where a.source_adapter=?
         order by m.session_id,m.ordinal,m.row_id"""
    return list(conn.execute(q,(adapter,)))

def artifact_stats(conn,adapter):
    if adapter is None:
        rows=conn.execute("select source_adapter,count(*),coalesce(sum(observed_message_count),0) from artifacts group by source_adapter order by source_adapter").fetchall()
    else:
        rows=conn.execute("select source_adapter,count(*),coalesce(sum(observed_message_count),0) from artifacts where source_adapter=? group by source_adapter order by source_adapter",(adapter,)).fetchall()
    return {"count":sum(int(r[1]) for r in rows),"by_adapter":{str(r[0]):{"artifacts":int(r[1]),"observed_messages":int(r[2])} for r in rows}}

def episode_stats(rows):
    by=collections.defaultdict(list)
    for r in rows:
        by[str(r["session_id"])].append(r)
    totals=collections.Counter(); sigs=[]
    for sr in by.values():
        starts=[i for i,r in enumerate(sr) if r["role"]=="user" and r["search_class"]=="dialogue" and r["content_type"]=="text"]
        for p,start in enumerate(starts):
            end=starts[p+1] if p+1<len(starts) else len(sr)
            win=sr[start:end]
            if not any(r["role"]=="assistant" and r["search_class"]=="dialogue" and r["content_type"]=="text" for r in win):
                continue
            totals["eligible_user_turn_episodes"]+=1
            tools=[r for r in win if r["role"]=="tool" and r["search_class"]=="evidence"]
            if tools:
                totals["episodes_with_observed_tool_evidence"]+=1
            else:
                totals["episodes_without_observed_tool_evidence"]+=1
            if any(r["content_type"]=="execution_output" for r in tools):
                totals["episodes_with_execution_output"]+=1
            if any(r["search_class"]=="trace" for r in win):
                totals["episodes_with_trace"]+=1
            payload="\n".join(str(r["canonical_message_sha256"]) for r in win if r["search_class"]!="hidden").encode()
            sigs.append(hashlib.sha256(payload).hexdigest())
    uniq=set(sigs)
    totals["unique_episode_signatures"]=len(uniq)
    totals["duplicate_episode_instances"]=len(sigs)-len(uniq)
    return dict(sorted(totals.items())),uniq

def source_inventory(spec):
    if not spec.path.is_file():
        raise ValueError(f"missing corpus DB for {spec.name}: {spec.path}")
    conn=sqlite3.connect(f"file:{spec.path}?mode=ro",uri=True)
    conn.row_factory=sqlite3.Row
    try:
        schema=validate_schema(conn)
        rows=selected_rows(conn,spec.adapter)
        if not rows:
            raise ValueError(f"source {spec.name} selected zero messages")
        sessions={str(r["session_id"]) for r in rows}
        hashes=[str(r["canonical_message_sha256"]) for r in rows if r["canonical_message_sha256"]]
        uniq_hashes=set(hashes)
        shape=collections.Counter((str(r["role"]),str(r["content_type"]),str(r["search_class"])) for r in rows)
        coverage=collections.Counter(str(state) for sid,state in conn.execute("select session_id,coverage_state from sessions") if str(sid) in sessions)
        branch={s for s in sessions if "~branch-" in s}
        obs=sum(n for (role,ctype,sclass),n in shape.items() if role in {"user","assistant"} and ctype=="text" and sclass=="dialogue")
        tool=sum(n for (role,_c,sclass),n in shape.items() if role=="tool" and sclass=="evidence")
        hidden=sum(n for (_r,_c,sclass),n in shape.items() if sclass=="hidden")
        trace=sum(n for (_r,_c,sclass),n in shape.items() if sclass=="trace")
        eps,epsigs=episode_stats(rows)
        eligible=int(eps.get("eligible_user_turn_episodes",0))
        tool_eps=int(eps.get("episodes_with_observed_tool_evidence",0))
        report={
          "provider":spec.name,
          "source_adapter_filter":spec.adapter,
          "database":{"bytes":spec.path.stat().st_size,"sha256":sha256_file(spec.path),"schema_version":schema},
          "artifacts":artifact_stats(conn,spec.adapter),
          "sessions":{"selected":len(sessions),"coverage":dict(sorted(coverage.items())),"branch_session_ids":len(branch),"branch_roots":len({s.split("~branch-",1)[0] for s in branch})},
          "messages":{"selected":len(rows),"unique_canonical_hashes":len(uniq_hashes),"duplicate_hash_instances":len(hashes)-len(uniq_hashes),"observable_dialogue_text":obs,"tool_evidence":tool,"trace":trace,"hidden_excluded_from_projection":hidden,
                      "shape":[{"role":k[0],"content_type":k[1],"search_class":k[2],"count":n} for k,n in sorted(shape.items())]},
          "candidate_episodes":{**eps,"observed_tool_evidence_fraction":{"numerator":tool_eps,"denominator":eligible} if eligible else None,"tool_observability":"EXPOSED" if tool>0 else "NOT_EXPOSED_OR_ABSENT"}
        }
        return report,uniq_hashes,epsigs
    finally:
        conn.close()

def overlap_matrix(sets):
    names=sorted(sets); out=[]
    for i,left in enumerate(names):
        for right in names[i+1:]:
            out.append({"left":left,"right":right,"shared":len(sets[left]&sets[right])})
    return out

def build_inventory(sources,heldout_files):
    reports=[]; msets={}; esets={}
    for s in sources:
        report,m,e=source_inventory(s)
        reports.append(report); msets[s.name]=m; esets[s.name]=e
    held=[]
    for p in heldout_files:
        if not p.is_file():
            raise ValueError(f"missing heldout binding: {p}")
        held.append({"path":p.as_posix(),"bytes":p.stat().st_size,"sha256":sha256_file(p)})
    total=sum(int(r["candidate_episodes"].get("eligible_user_turn_episodes",0)) for r in reports)
    return {
      "schema_version":SCHEMA,
      "purpose":"issue_26_realistic_sft_preflight_only",
      "authority":"INVENTORY_ONLY_NO_TRAINING_AUTHORIZATION",
      "sources":reports,
      "cross_provider_overlap":{"canonical_message_hashes":overlap_matrix(msets),"episode_signatures":overlap_matrix(esets)},
      "projection_policy":{
        "allowed_observable_inputs":["user_text_dialogue","assistant_text_dialogue","tool_evidence","observable_trace_metadata"],
        "excluded_from_training_projection":["hidden_thoughts","reasoning_recap","system_messages","model_editable_context","user_editable_context"],
        "raw_corpus_is_ground_truth":False,
        "provider_is_authority":False,
        "no_observed_tool_evidence_means_no_call":False},
      "decision_label_inventory":{
        "state":"NOT_ADJUDICATED","PROBE":None,"READY":None,"UNKNOWN":None,"NO_CALL":None,
        "reason":"historical provider actions are evidence, not authoritative PROBE/READY/UNKNOWN/NO_CALL labels"},
      "leakage_boundary":{"bound_heldout_files":held,"semantic_near_duplicate_screening":"REQUIRED_BEFORE_DATASET_PROJECTION","split_unit":"session_plus_semantic_family"},
      "privacy":{"raw_sources":"PRIVATE_HISTORICAL_INTERACTION","committed_inventory":"METADATA_ONLY_NO_RAW_TEXT","projected_examples":"NOT_YET_CLASSIFIED","public_dataset_authorized":False},
      "candidate_pool":{"eligible_user_turn_episodes_across_sources":total,"status":"PRE_ADJUDICATION"},
      "next_gate":{"required":["deterministic_candidate_projection_contract","privacy_publicability_review","semantic_family_adjudication","PROBE_READY_UNKNOWN_NO_CALL_label_adjudication","provider_and_family_balanced_split","near_duplicate_leakage_check"],"training_authorized":False}
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",action="append",default=[])
    p.add_argument("--source-adapter",action="append",default=[])
    p.add_argument("--heldout-file",action="append",default=[],type=pathlib.Path)
    p.add_argument("--output",required=True,type=pathlib.Path)
    a=p.parse_args()
    paths=parse_mapping(a.source,"--source")
    adapters=parse_mapping(a.source_adapter,"--source-adapter")
    unknown=sorted(set(adapters)-set(paths))
    if unknown:
        raise ValueError(f"adapter supplied for unknown sources: {unknown}")
    sources=[SourceSpec(name,pathlib.Path(path),adapters.get(name)) for name,path in sorted(paths.items())]
    if len(sources)<2:
        raise ValueError("at least two providers are required")
    inv=build_inventory(sources,a.heldout_file)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(inv,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(f"NEEDLE3_MULTIPROVIDER_INVENTORY_PASS sources={len(sources)} episodes={inv['candidate_pool']['eligible_user_turn_episodes_across_sources']}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
