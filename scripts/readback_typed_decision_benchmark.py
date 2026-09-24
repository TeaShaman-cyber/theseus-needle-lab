#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts import typed_decision_benchmark as bench

SHA40_RE=re.compile(r'^[0-9a-f]{40}$')

def run_checked(cmd: list[str]) -> None:
    subprocess.run(cmd,cwd=ROOT,check=True,text=True)

def verify_sums(root: Path, sums: Path) -> dict[str,str]:
    observed={}
    for line in sums.read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        parts=line.split('  ',1)
        if len(parts)!=2: raise ValueError('invalid SHA256SUMS line')
        digest,name=parts; bench.require_sha256(digest,'SHA256SUMS digest')
        path=root/name
        if not path.is_file(): raise ValueError(f'SHA256SUMS file missing: {name}')
        if bench.sha256_file(path)!=digest: raise ValueError(f'SHA256SUMS mismatch: {name}')
        observed[name]=digest
    required={'raw-results.jsonl','normalized-results.jsonl','runtime-receipt.json','resource-receipt.json','serialization-receipt.json'}
    if set(observed)!=required: raise ValueError('SHA256SUMS coverage mismatch')
    return observed

def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--experiment-sha',required=True); p.add_argument('--launcher-sha',required=True); p.add_argument('--run-id',required=True); p.add_argument('--run-attempt',required=True); p.add_argument('--out',type=Path,required=True); a=p.parse_args()
    if SHA40_RE.fullmatch(a.experiment_sha) is None or SHA40_RE.fullmatch(a.launcher_sha) is None: raise SystemExit('experiment/launcher SHA invalid')
    manifest=bench.validate_manifest(); cases=bench.load_cases(ROOT/manifest['primary_suite']['path'],primary=True); registry=bench.load_registry(ROOT/manifest['candidate_registry']['path'])
    entries=[]
    for cid in manifest['included_candidates']:
        matches=sorted(a.root.glob(f'typed-decision-v1-{cid}-{a.run_id}-{a.run_attempt}'))
        if len(matches)!=1:
            entries.append({'candidate_id':cid,'evidence_state':'BLOCKED','reason':'ARTIFACT_MISSING_OR_AMBIGUOUS','artifact_matches':len(matches)}); continue
        artifact_root=matches[0]; result_root=artifact_root/'_benchmark'/cid; telemetry_root=artifact_root/'_telemetry'/cid; checkpoint=telemetry_root/'checkpoint.json'; heartbeat=telemetry_root/'heartbeat.jsonl'
        if not checkpoint.is_file():
            entries.append({'candidate_id':cid,'evidence_state':'BLOCKED','reason':'CHECKPOINT_MISSING'}); continue
        cmd=[sys.executable,str(ROOT/'scripts'/'execution_telemetry.py'),'validate','--checkpoint',str(checkpoint),'--root',str(artifact_root),'--expected-experiment-sha',a.experiment_sha,'--expected-launcher-sha',a.launcher_sha,'--expected-stage','typed_decision_benchmark_v1','--expected-unit',cid]
        if heartbeat.is_file(): cmd.extend(['--heartbeat',str(heartbeat)])
        run_checked(cmd)
        cp=json.loads(checkpoint.read_text(encoding='utf-8')); status=cp.get('execution_status'); lifecycle=cp.get('lifecycle_state')
        entry={'candidate_id':cid,'execution_status':status,'lifecycle_state':lifecycle,'checkpoint_sha256':bench.sha256_file(checkpoint),'evidence_state':'VERIFIED_EXECUTION_RECORD'}
        if status=='SUCCEEDED':
            sums=result_root/'SHA256SUMS'
            if not sums.is_file(): raise ValueError(f'{cid}: SHA256SUMS missing')
            entry['artifact_sha256']=verify_sums(result_root,sums)
            rows=bench.validate_result_rows(bench.read_jsonl(result_root/'normalized-results.jsonl'),cases,cid,registry)
            entry['score']=bench.score(cases,rows); entry['resource_receipt']=bench.load_json(result_root/'resource-receipt.json'); entry['evidence_state']='MODEL_OR_DOMAIN_WITNESS_INPUT_VERIFIED'
        else:
            fault_out=a.out.parent/f'fault-{cid}.json'; fault_out.parent.mkdir(parents=True,exist_ok=True)
            proc=subprocess.run([sys.executable,str(ROOT/'scripts'/'integration_faults.py'),'classify-checkpoint','--checkpoint',str(checkpoint),'--output',str(fault_out)],cwd=ROOT,text=True)
            if proc.returncode==0 and fault_out.is_file(): entry['fault_receipt']=json.loads(fault_out.read_text(encoding='utf-8'))
        entries.append(entry)
    receipt={'schema':'theseus.typed-decision-benchmark-readback.v1','experiment_sha':a.experiment_sha,'launcher_sha':a.launcher_sha,'run_id':a.run_id,'run_attempt':a.run_attempt,'contract_sha256':manifest['contract']['sha256'],'primary_fixture_sha256':manifest['primary_suite']['sha256'],'legacy_fixture_sha256':manifest['legacy_compat_suite']['sha256'],'candidates':entries,'complete_local_matrix':all(e.get('evidence_state')=='MODEL_OR_DOMAIN_WITNESS_INPUT_VERIFIED' for e in entries),'acceptance_authority':False,'scientific_acceptance_performed':False}
    bench.write_json(a.out,receipt)

if __name__=='__main__': main()
