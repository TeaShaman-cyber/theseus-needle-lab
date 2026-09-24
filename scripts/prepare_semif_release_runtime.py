#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/'experiments'/'typed-decision-benchmark'/'v1'/'candidates.json'

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def tree_digest(root: Path) -> tuple[str,int,int]:
    h=hashlib.sha256(); count=0; total=0
    for path in sorted(p for p in root.rglob('*') if p.is_file()):
        rel=path.relative_to(root).as_posix(); digest=sha256_file(path); size=path.stat().st_size
        h.update(f'{rel}\0{size}\0{digest}\n'.encode('utf-8')); count+=1; total+=size
    return h.hexdigest(),count,total

def load_json(path: Path): return json.loads(path.read_text(encoding='utf-8'))

def load_helper(path: Path):
    spec=importlib.util.spec_from_file_location('theseus_artifact_package',path)
    if spec is None or spec.loader is None: raise SystemExit(f'cannot import package helper: {path}')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def verify_cookbook_head(root: Path, expected: str) -> None:
    observed=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    if observed!=expected: raise SystemExit(f'cookbook revision mismatch: {observed} != {expected}')

def download_public(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True,exist_ok=True)
    request=urllib.request.Request(url,headers={'User-Agent':'theseus-typed-decision-benchmark-v1'})
    with urllib.request.urlopen(request,timeout=180) as response, target.open('wb') as out:
        if response.status!=200: raise SystemExit(f'public release download HTTP {response.status}')
        shutil.copyfileobj(response,out)

def validate_build_receipt(receipt: dict, identity: dict, runtime_dir: Path) -> dict:
    if receipt.get('schema')!='theseus.typed-decision-toolchain-receipt.v1': raise SystemExit('unexpected SemIf build receipt schema')
    if receipt.get('status')!='BUILT': raise SystemExit('SemIf build receipt is not BUILT')
    if receipt.get('claim_scope')!='RUNTIME_PACKAGE_IDENTITY_ONLY': raise SystemExit('unexpected SemIf build claim scope')
    if receipt.get('acceptance_authority') is not False: raise SystemExit('SemIf build receipt carries authority')
    if receipt.get('source_revision')!=identity['source_revision']: raise SystemExit('SemIf source revision mismatch')
    lock=receipt.get('lock') or {}; site=receipt.get('site_packages') or {}; cpu=receipt.get('cpu_runtime') or {}; distributions=receipt.get('distributions') or {}
    if lock.get('sha256')!=identity['lock_sha256']: raise SystemExit('SemIf lock SHA mismatch')
    if site.get('tree_sha256')!=identity['tree_sha256']: raise SystemExit('SemIf declared tree SHA mismatch')
    if cpu.get('forbidden_cuda_packages')!=[] or cpu.get('torch_cuda') is not None: raise SystemExit('SemIf runtime is not CPU-only')
    if distributions.get('torch')!='2.10.0+cpu': raise SystemExit('SemIf Torch version mismatch')
    site_root=runtime_dir/'site-packages'
    if not site_root.is_dir(): raise SystemExit('SemIf runtime site-packages missing')
    tree,count,total=tree_digest(site_root)
    if tree!=identity['tree_sha256']: raise SystemExit('SemIf extracted tree SHA mismatch')
    if count!=site.get('file_count') or total!=site.get('bytes'): raise SystemExit('SemIf extracted tree geometry mismatch')
    return {'tree_sha256':tree,'file_count':count,'bytes':total,'lock_sha256':lock.get('sha256'),'torch':distributions.get('torch')}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--cookbook-root',type=Path,required=True); p.add_argument('--archive',type=Path,required=True); p.add_argument('--checksum-file',type=Path,required=True); p.add_argument('--runtime-dir',type=Path,required=True); p.add_argument('--out',type=Path,required=True); a=p.parse_args()
    registry=load_json(REGISTRY); identity=registry['candidates']['semif_qwen3_0_6b_q8']['runtime_identity']
    if identity.get('distribution')!='PUBLIC_GITHUB_RELEASE': raise SystemExit('SemIf distribution is not public Release')
    verify_cookbook_head(a.cookbook_root,identity['cookbook_revision']); helper=load_helper(a.cookbook_root/identity['cookbook_helper'])
    started=time.monotonic_ns(); download_public(identity['release_url'],a.archive); download_public(identity['release_checksum_url'],a.checksum_file)
    observed=sha256_file(a.archive); expected=identity['release_asset_digest'].removeprefix('sha256:')
    if observed!=expected or observed!=identity['tar_sha256']: raise SystemExit('SemIf Release tar SHA mismatch')
    if sha256_file(a.checksum_file)!=identity['release_checksum_digest'].removeprefix('sha256:'): raise SystemExit('SemIf Release checksum asset digest mismatch')
    declared=a.checksum_file.read_text(encoding='utf-8').strip().split()
    if len(declared)!=2 or declared[0]!=observed or declared[1]!='semif-cpu-toolchain.tar.gz': raise SystemExit('SemIf checksum file content mismatch')
    shutil.rmtree(a.runtime_dir,ignore_errors=True); helper.safe_extract_tar(a.archive,a.runtime_dir)
    receipt_path=a.runtime_dir/'build-receipt.json'
    if not receipt_path.is_file(): raise SystemExit('SemIf build receipt missing')
    verification=validate_build_receipt(load_json(receipt_path),identity,a.runtime_dir)
    consumer={'schema':'theseus.typed-decision-release-consumer-receipt.v1','status':'READY','claim_scope':'RUNTIME_RELEASE_CONSUMPTION_ONLY','acceptance_authority':False,'setup_ms':(time.monotonic_ns()-started)//1_000_000,'source_revision':identity['source_revision'],'release':{k:identity[k] for k in ('release_repository','release_id','release_tag','release_target_commit','release_asset_id','release_asset_name','release_asset_size','release_asset_digest','release_url','release_checksum_asset_id','release_checksum_digest','release_checksum_url')},'producer':{k:identity[k] for k in ('producer_run_id','producer_head_sha','producer_actions_artifact_id','producer_actions_artifact_digest')},'cookbook':{'revision':identity['cookbook_revision'],'helper':identity['cookbook_helper']},'verification':{'tar_sha256':observed,'runtime':verification}}
    a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(consumer,indent=2,sort_keys=True)+'\n',encoding='utf-8')

if __name__=='__main__': main()
