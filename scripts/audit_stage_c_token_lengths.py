from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import pathlib

from scripts.audit_realistic_sft_token_lengths import audit_examples

EXPECTED_NEEDLE_VERSION = "2.0.8"


def _load_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha256(path: pathlib.Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def bind_stage_c_rows(projection_rows: list[dict], canonical_rows: list[dict], prefix: str) -> list[dict]:
    if len(projection_rows) != len(canonical_rows):
        raise RuntimeError("DATASET_ALIGNMENT_FAILED: Stage C projection/canonical row count differs")
    out=[]
    for projection, canonical in zip(projection_rows,canonical_rows):
        state=canonical.get('canonical_state',{})
        expected_query=(prefix+canonical['query']) if state.get('applicability')=='ROUTE' else canonical['query']
        if projection.get('query') != expected_query:
            raise RuntimeError("DATASET_ALIGNMENT_FAILED: Stage C query mismatch")
        out.append({'case_id':canonical['case_id'],'example':projection})
    return out


def runtime_audit(projection_path: pathlib.Path, canonical_path: pathlib.Path, prefix_path: pathlib.Path, max_len: int) -> dict:
    from needle.model.finetune import render_example
    from needle.model.tokenizer import get_tokenizer

    version=importlib.metadata.version('cactus-needle')
    if version != EXPECTED_NEEDLE_VERSION:
        raise RuntimeError(f"RUNTIME_DRIFT: cactus-needle={version} expected={EXPECTED_NEEDLE_VERSION}")
    projection=_load_jsonl(projection_path)
    canonical=_load_jsonl(canonical_path)
    prefix=prefix_path.read_text(encoding='utf-8')
    rows=bind_stage_c_rows(projection,canonical,prefix)
    tokenizer=get_tokenizer()
    result=audit_examples(rows,tokenizer,render_example,max_len)
    model_path=pathlib.Path(tokenizer.model_path)
    result['runtime']={
        'cactus_needle':version,
        'tokenizer_model_path':str(model_path),
        'tokenizer_model_sha256':_sha256(model_path),
        'tokenizer_md5':tokenizer.md5,
    }
    result['inputs']={
        'projection_sha256':_sha256(projection_path),
        'canonical_sha256':_sha256(canonical_path),
        'prefix_sha256':_sha256(prefix_path),
    }
    return result


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--projection',type=pathlib.Path,required=True)
    p.add_argument('--canonical',type=pathlib.Path,required=True)
    p.add_argument('--prefix',type=pathlib.Path,default=pathlib.Path('experiments/needle-realistic-sft/contract/route-positive-prefix.txt'))
    p.add_argument('--max-len',type=int,default=256)
    p.add_argument('--output',type=pathlib.Path,required=True)
    args=p.parse_args()
    result=runtime_audit(args.projection,args.canonical,args.prefix,args.max_len)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','row_count','max_observed_tokens','truncated_case_ids')},sort_keys=True))
    return 0 if result['status']=='VERIFIED_ZERO_TRUNCATION' else 2


if __name__=='__main__':
    raise SystemExit(main())
