#!/usr/bin/env bash
set -euo pipefail

: "${EXPERIMENT_SHA:?EXPERIMENT_SHA is required}"
: "${LAUNCHER_SHA:?LAUNCHER_SHA is required}"
: "${REPLICA_ID:?REPLICA_ID is required}"
case "$REPLICA_ID" in
  R1|R2) ;;
  *) echo "BLOCKED_INVALID_REPLICA_ID"; exit 2 ;;
esac

mkdir -p checkpoints artifacts results logs metrics
python -m pip install "cactus-needle[train]==2.0.8" 2>&1 | tee logs/install.log
python3 scripts/validate_realistic_sft_dataset.py
python3 scripts/audit_realistic_sft_token_lengths.py --max-len 256 --output results/token-length-audit.json
python3 - <<'PY'
import json
r=json.load(open('results/token-length-audit.json'))
assert r['status']=='VERIFIED_ZERO_TRUNCATION'
assert r['truncated_case_ids']==[]
PY
python - <<'PY' 2>&1 | tee logs/checkpoint-download.log
from huggingface_hub import hf_hub_download
print(hf_hub_download('Cactus-Compute/needle2','checkpoints/needle2.pkl',repo_type='model',local_dir='.'))
PY
checkpoint_expected=4b0a972d163ffc7678fb3c36bace508114872e9d2ce9e10f225825752d3795bc
checkpoint_actual=$(sha256sum checkpoints/needle2.pkl | awk '{print $1}')
test "$checkpoint_actual" = "$checkpoint_expected"
train_sha=$(sha256sum experiments/needle-realistic-sft/data/train.needle.jsonl | awk '{print $1}')

adapter="artifacts/adapter-${REPLICA_ID}.pkl"
cact="artifacts/tuned-${REPLICA_ID}.cact"
/usr/bin/time -v -o metrics/train.time \
  python scripts/run_seeded_finetune.py experiments/needle-realistic-sft/data/train.needle.jsonl \
    --checkpoint checkpoints/needle2.pkl --seed 0 --epochs 15 --batch-size 16 --lr 1e-4 \
    --lora-rank 16 --lora-alpha 32 --max-len 256 --val-split 0.1 \
    --out "$adapter" 2>&1 | tee logs/train.log

/usr/bin/time -v -o metrics/build.time \
  needle build checkpoints/needle2.pkl --lora "$adapter" --out "$cact" \
  2>&1 | tee logs/build.log

adapter_sha=$(sha256sum "$adapter" | awk '{print $1}')
cact_sha=$(sha256sum "$cact" | awk '{print $1}')
python3 - <<'PY' > metrics/parsed-resource.json
import json,re

def parse(path):
    t=open(path,encoding='utf-8',errors='replace').read()
    rss=re.search(r'Maximum resident set size \(kbytes\):\s*(\d+)',t)
    elapsed=re.search(r'Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*([^\n]+)',t)
    def secs(v):
        p=v.strip().split(':')
        if len(p)==2:return int(p[0])*60+float(p[1])
        return int(p[0])*3600+int(p[1])*60+float(p[2])
    return {'elapsed':secs(elapsed.group(1)),'rss':int(rss.group(1)) if rss else None}
print(json.dumps({'train':parse('metrics/train.time'),'build':parse('metrics/build.time')}))
PY
train_elapsed=$(python3 -c "import json;print(json.load(open('metrics/parsed-resource.json'))['train']['elapsed'])")
train_rss=$(python3 -c "import json;print(json.load(open('metrics/parsed-resource.json'))['train']['rss'])")
build_elapsed=$(python3 -c "import json;print(json.load(open('metrics/parsed-resource.json'))['build']['elapsed'])")
python3 scripts/realistic_sft_replica_train_receipt.py \
  --replica-id "$REPLICA_ID" --experiment-commit "$EXPERIMENT_SHA" --launcher-commit "$LAUNCHER_SHA" \
  --run-id "${GITHUB_RUN_ID:-LOCAL}" --train-sha256 "$train_sha" --checkpoint-sha256 "$checkpoint_actual" \
  --adapter-sha256 "$adapter_sha" --cact-sha256 "$cact_sha" \
  --train-elapsed-seconds "$train_elapsed" --train-max-rss-kb "$train_rss" \
  --build-elapsed-seconds "$build_elapsed" --output "results/train-receipt-${REPLICA_ID}.json"
