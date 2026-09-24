#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import resource
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts import typed_decision_benchmark as bench

def tree_bytes(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob('*') if p.is_file())

def setup_ms() -> int | None:
    value=os.environ.get('SETUP_MS')
    return int(value) if value else None

def finalize(out_dir: Path, candidate_id: str, cases, raw_rows, normalized_rows, runtime_receipt, resource_receipt) -> None:
    manifest=bench.validate_manifest()
    registry=bench.load_registry(ROOT/manifest['candidate_registry']['path'])
    candidate=registry['candidates'][candidate_id]
    validated=bench.validate_result_rows(normalized_rows,cases,candidate_id,registry)
    out_dir.mkdir(parents=True,exist_ok=True)
    bench.write_jsonl(out_dir/'raw-results.jsonl',raw_rows)
    bench.write_jsonl(out_dir/'normalized-results.jsonl',[{k:v for k,v in row.items() if not k.startswith('_')} for row in validated])
    bench.write_json(out_dir/'runtime-receipt.json',runtime_receipt)
    bench.write_json(out_dir/'resource-receipt.json',resource_receipt)
    bench.write_json(out_dir/'serialization-receipt.json',{
        'schema':'theseus.typed-decision-benchmark-serialization.v1',
        'candidate_id':candidate_id,'adapter':candidate['adapter'],'acceptance_authority':False,
        'rows':[{'case_id':row['case_id'],**{k:row['provider_serialization'][k] for k in ('input_sha256','request_sha256','response_sha256')}} for row in normalized_rows],
    })
    files=['raw-results.jsonl','normalized-results.jsonl','runtime-receipt.json','resource-receipt.json','serialization-receipt.json']
    (out_dir/'SHA256SUMS').write_text(''.join(f'{bench.sha256_file(out_dir/name)}  {name}\n' for name in files),encoding='utf-8')

def run_baseline(out_dir: Path) -> None:
    manifest=bench.validate_manifest(); cases=bench.load_cases(ROOT/manifest['primary_suite']['path'],primary=True)
    registry=bench.load_registry(ROOT/manifest['candidate_registry']['path']); cid='baseline_constant_unknown'; candidate=registry['candidates'][cid]
    raw=[]; normalized=[]
    for case in cases:
        request={'query':case['query'],'baseline':'constant-UNKNOWN'}; response={'decision':'UNKNOWN'}
        raw.append({'case_id':case['case_id'],'request':request,'response':response})
        normalized.append(bench.build_result(case,cid,candidate,'UNKNOWN',request,response,probabilities=None,latency_ms=0.0,resource_receipt_ref='resource-receipt.json'))
    runtime={'schema':'theseus.typed-decision-benchmark-runtime.v1','candidate_id':cid,'runtime_identity':candidate['runtime_identity'],'model_identity':candidate['model_identity'],'python':platform.python_version(),'platform':platform.platform(),'acceptance_authority':False}
    resource_receipt={'schema':'theseus.typed-decision-benchmark-resource.v1','candidate_id':cid,'setup_ms':setup_ms(),'load_ms':0.0,'per_case_latency_ms':[0.0]*len(cases),'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'model_artifact_bytes':(ROOT/manifest['baseline']['path']).stat().st_size,'acceptance_authority':False}
    finalize(out_dir,cid,cases,raw,normalized,runtime,resource_receipt)

def run_needle(out_dir: Path, checkpoint: Path) -> None:
    from scripts import needle3_deployment_canary as nc
    from needle.model.architecture import SimpleAttentionNetwork
    from needle.model.run import build_prompt, generate, load_checkpoint
    from needle.model.tokenizer import get_tokenizer
    manifest=bench.validate_manifest(); cases=bench.load_cases(ROOT/manifest['primary_suite']['path'],primary=True)
    registry=bench.load_registry(ROOT/manifest['candidate_registry']['path']); cid='needle3_base'; candidate=registry['candidates'][cid]
    observed=importlib.metadata.version('cactus-needle')
    if observed != candidate['runtime_identity']['package_version']: raise SystemExit(f'Needle package mismatch: {observed}')
    if bench.sha256_file(checkpoint) != candidate['model_identity']['sha256']: raise SystemExit('Needle checkpoint SHA mismatch')
    load_start=time.perf_counter(); params,config=load_checkpoint(str(checkpoint)); model=SimpleAttentionNetwork(config); tokenizer=get_tokenizer(config.vocab_size); load_ms=(time.perf_counter()-load_start)*1000.0
    route_tool={'name':'route','description':'Classify current evidence. PROBE = current verification is needed and safely possible. READY = current authoritative evidence verifies the state. UNKNOWN = evidence is insufficient and no safe current probe is available. Do not call route when evidence routing is not applicable.','parameters':{'type':'object','properties':{'decision':{'type':'string','enum':['PROBE','READY','UNKNOWN']}},'required':['decision']}}
    raw=[]; normalized=[]; latencies=[]
    for case in cases:
        request={'query':case['query'],'tools':[route_tool]}; prompt=build_prompt(case['query'],[route_tool])
        started=time.perf_counter(); text=generate(model,params,tokenizer,prompt,max_new_tokens=128,temperature=0.0,seed=0,stream=False); latency=(time.perf_counter()-started)*1000.0
        response=nc.reference_text_to_response(text); native=nc.classify_response(response); label=native if native in bench.CLASSES else 'ERROR'
        raw.append({'case_id':case['case_id'],'request':request,'response':response,'native_prediction':native,'latency_ms':latency}); latencies.append(latency)
        normalized.append(bench.build_result(case,cid,candidate,label,request,response,probabilities=None,latency_ms=latency,resource_receipt_ref='resource-receipt.json'))
    runtime={'schema':'theseus.typed-decision-benchmark-runtime.v1','candidate_id':cid,'runtime_identity':candidate['runtime_identity'],'model_identity':candidate['model_identity'],'python':platform.python_version(),'platform':platform.platform(),'acceptance_authority':False}
    resource_receipt={'schema':'theseus.typed-decision-benchmark-resource.v1','candidate_id':cid,'setup_ms':setup_ms(),'load_ms':load_ms,'per_case_latency_ms':latencies,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'model_artifact_bytes':checkpoint.stat().st_size,'acceptance_authority':False}
    finalize(out_dir,cid,cases,raw,normalized,runtime,resource_receipt)

def run_kev(out_dir: Path, checkpoint_id: str, threads: int) -> None:
    import torch
    from kev.checkpoint import Checkpoint, LoadOptions, resolve_run
    manifest=bench.validate_manifest(); cases=bench.load_cases(ROOT/manifest['primary_suite']['path'],primary=True)
    registry=bench.load_registry(ROOT/manifest['candidate_registry']['path']); cid='kev_0_8b'; candidate=registry['candidates'][cid]; ident=candidate['model_identity']
    expected=f"{ident['checkpoint']}@{ident['checkpoint_revision']}"
    if checkpoint_id != expected: raise SystemExit('Kev checkpoint request identity mismatch')
    torch.set_num_threads(threads); ck=Checkpoint(checkpoint_id)
    if ck.meta.base != ident['base'] or ck.meta.base_revision != ident['base_revision']: raise SystemExit('Kev base identity mismatch')
    load_start=time.perf_counter(); tok,model=ck.load('cpu',LoadOptions(dtype=torch.float32,merge=False,backend='torch')); load_ms=(time.perf_counter()-load_start)*1000.0
    raw=[]; normalized=[]; latencies=[]
    for case in cases:
        question={'instr':case['query'],'options':[bench.OPTION_DESCRIPTIONS[label] for label in bench.CLASSES],'label':0}
        request={'state':bench.SHARED_STATE,'questions':[question]}; enc=model.encode(tok,request)
        if enc.get('labels') != [0]: raise SystemExit('Kev dummy label invariant failed')
        enc=dict(enc); enc.pop('labels',None)
        started=time.perf_counter(); probs=model.probs(enc)[0].detach().cpu().tolist(); latency=(time.perf_counter()-started)*1000.0
        class_probs=bench.validate_probabilities(dict(zip(bench.CLASSES,probs))); label=bench.normalized_choice(class_probs)
        response={'option_ids':list(bench.CLASSES),'probabilities':[class_probs[x] for x in bench.CLASSES]}
        raw.append({'case_id':case['case_id'],'request':request,'response':response,'latency_ms':latency}); latencies.append(latency)
        normalized.append(bench.build_result(case,cid,candidate,label,request,response,probabilities=class_probs,latency_ms=latency,resource_receipt_ref='resource-receipt.json'))
    adapter_path=Path(ck.path); base_path=Path(resolve_run(f"{ck.meta.base}@{ck.meta.base_revision}"))
    runtime={'schema':'theseus.typed-decision-benchmark-runtime.v1','candidate_id':cid,'runtime_identity':candidate['runtime_identity'],'model_identity':candidate['model_identity'],'python':platform.python_version(),'platform':platform.platform(),'torch':torch.__version__,'acceptance_authority':False}
    resource_receipt={'schema':'theseus.typed-decision-benchmark-resource.v1','candidate_id':cid,'setup_ms':setup_ms(),'load_ms':load_ms,'per_case_latency_ms':latencies,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'model_artifact_bytes':tree_bytes(adapter_path)+tree_bytes(base_path),'model_artifact_components':{'adapter_snapshot_bytes':tree_bytes(adapter_path),'base_snapshot_bytes':tree_bytes(base_path)},'acceptance_authority':False}
    finalize(out_dir,cid,cases,raw,normalized,runtime,resource_receipt)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--candidate',choices=('baseline_constant_unknown','needle3_base','kev_0_8b'),required=True); p.add_argument('--out-dir',type=Path,required=True); p.add_argument('--checkpoint',type=Path); p.add_argument('--kev-checkpoint'); p.add_argument('--threads',type=int,default=4); a=p.parse_args()
    if a.candidate=='baseline_constant_unknown': run_baseline(a.out_dir)
    elif a.candidate=='needle3_base':
        if a.checkpoint is None: p.error('--checkpoint required for needle3_base')
        run_needle(a.out_dir,a.checkpoint)
    else:
        if not a.kev_checkpoint: p.error('--kev-checkpoint required for kev_0_8b')
        run_kev(a.out_dir,a.kev_checkpoint,a.threads)

if __name__=='__main__': main()
