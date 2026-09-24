#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts import typed_decision_benchmark as bench

def main():
    p=argparse.ArgumentParser(); p.add_argument('--native-input',type=Path,required=True); p.add_argument('--native-output',type=Path,required=True); p.add_argument('--runtime-package-receipt',type=Path,required=True); p.add_argument('--gguf',type=Path,required=True); p.add_argument('--out-dir',type=Path,required=True); a=p.parse_args()
    manifest=bench.validate_manifest(); cases=bench.load_cases(ROOT/manifest['primary_suite']['path'],primary=True); registry=bench.load_registry(ROOT/manifest['candidate_registry']['path']); cid='semif_qwen3_0_6b_q8'; candidate=registry['candidates'][cid]
    expected_input=[bench.semif_row(case) for case in cases]; observed_input=bench.read_jsonl(a.native_input)
    if observed_input != expected_input: raise SystemExit('SemIf native input differs from frozen adapter projection')
    outputs=bench.read_jsonl(a.native_output)
    if len(outputs)!=len(cases): raise SystemExit('SemIf output coverage mismatch')
    package=bench.load_json(a.runtime_package_receipt); runtime_id=candidate['runtime_identity']
    if package.get('schema')!='theseus.typed-decision-release-consumer-receipt.v1' or package.get('status')!='READY': raise SystemExit('SemIf runtime release receipt invalid')
    if package.get('claim_scope')!='RUNTIME_RELEASE_CONSUMPTION_ONLY' or package.get('acceptance_authority') is not False: raise SystemExit('SemIf runtime release receipt authority mismatch')
    ver=package.get('verification') or {}; release=package.get('release') or {}; runtime=ver.get('runtime') or {}
    checks=[release.get('release_id')==runtime_id['release_id'],release.get('release_asset_id')==runtime_id['release_asset_id'],release.get('release_asset_digest')==runtime_id['release_asset_digest'],ver.get('tar_sha256')==runtime_id['tar_sha256'],runtime.get('lock_sha256')==runtime_id['lock_sha256'],runtime.get('tree_sha256')==runtime_id['tree_sha256']]
    if not all(checks): raise SystemExit('SemIf runtime identity mismatch')
    if bench.sha256_file(a.gguf)!=candidate['model_identity']['gguf_sha256']: raise SystemExit('SemIf GGUF SHA mismatch')
    raw=[]; normalized=[]; latencies=[]
    for case,request,response in zip(cases,observed_input,outputs):
        if response.get('id')!=case['case_id'] or response.get('option_ids')!=list(bench.CLASSES): raise SystemExit('SemIf row identity/options mismatch')
        probs=response.get('probabilities')
        if not isinstance(probs,list) or len(probs)!=4: raise SystemExit('SemIf probability shape mismatch')
        class_probs=bench.validate_probabilities(dict(zip(bench.CLASSES,probs))); label=bench.normalized_choice(class_probs)
        seconds=response.get('total_seconds')
        if isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not math.isfinite(float(seconds)) or float(seconds)<0: raise SystemExit('SemIf total_seconds invalid')
        latency=float(seconds)*1000.0; latencies.append(latency)
        raw.append({'case_id':case['case_id'],'request':request,'response':response,'latency_ms':latency})
        normalized.append(bench.build_result(case,cid,candidate,label,request,response,probabilities=class_probs,latency_ms=latency,resource_receipt_ref='resource-receipt.json'))
    validated=bench.validate_result_rows(normalized,cases,cid,registry)
    out=a.out_dir; out.mkdir(parents=True,exist_ok=True); bench.write_jsonl(out/'raw-results.jsonl',raw); bench.write_jsonl(out/'normalized-results.jsonl',[{k:v for k,v in row.items() if not k.startswith('_')} for row in validated])
    bench.write_json(out/'runtime-receipt.json',{'schema':'theseus.typed-decision-benchmark-runtime.v1','candidate_id':cid,'runtime_identity':candidate['runtime_identity'],'model_identity':candidate['model_identity'],'python':platform.python_version(),'platform':platform.platform(),'runtime_package_receipt_sha256':bench.sha256_file(a.runtime_package_receipt),'acceptance_authority':False})
    setup_value=os.environ.get('SETUP_MS'); setup_total=int(setup_value) if setup_value is not None else None
    bench.write_json(out/'resource-receipt.json',{'schema':'theseus.typed-decision-benchmark-resource.v1','candidate_id':cid,'setup_ms':setup_total,'runtime_package_setup_ms':package.get('setup_ms'),'load_ms':None,'per_case_latency_ms':latencies,'peak_rss_kib':None,'peak_rss_status':'UNAVAILABLE_SEPARATE_INFERENCE_PROCESS','model_artifact_bytes':a.gguf.stat().st_size,'acceptance_authority':False})
    bench.write_json(out/'serialization-receipt.json',{'schema':'theseus.typed-decision-benchmark-serialization.v1','candidate_id':cid,'adapter':candidate['adapter'],'acceptance_authority':False,'rows':[{'case_id':row['case_id'],**{k:row['provider_serialization'][k] for k in ('input_sha256','request_sha256','response_sha256')}} for row in normalized]})
    files=['raw-results.jsonl','normalized-results.jsonl','runtime-receipt.json','resource-receipt.json','serialization-receipt.json']; (out/'SHA256SUMS').write_text(''.join(f'{bench.sha256_file(out/name)}  {name}\n' for name in files),encoding='utf-8')

if __name__=='__main__': main()
