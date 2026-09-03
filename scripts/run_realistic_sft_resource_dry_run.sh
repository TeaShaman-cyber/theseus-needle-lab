#!/usr/bin/env bash
set -euo pipefail

mkdir -p checkpoints artifacts results logs metrics

python -m pip install "cactus-needle[train]==2.0.8" 2>&1 | tee logs/install.log
python - <<'PY' | tee logs/package-versions.log
import importlib.metadata, platform
print('python=' + platform.python_version())
for name in ['cactus-needle','jax','jaxlib','flax','optax','numpy','sentencepiece','huggingface-hub']:
    print(f'{name}={importlib.metadata.version(name)}')
PY

python3 scripts/validate_realistic_sft_dataset.py
python3 scripts/audit_realistic_sft_token_lengths.py --max-len 256 --output results/token-length-audit.json
python3 - <<'PY'
import json
r=json.load(open('results/token-length-audit.json'))
assert r['status'] == 'VERIFIED_ZERO_TRUNCATION'
assert r['truncated_case_ids'] == []
PY

python - <<'PY' 2>&1 | tee logs/checkpoint-download.log
from huggingface_hub import hf_hub_download
print(hf_hub_download('Cactus-Compute/needle2','checkpoints/needle2.pkl',repo_type='model',local_dir='.'))
PY
expected=4b0a972d163ffc7678fb3c36bace508114872e9d2ce9e10f225825752d3795bc
actual=$(sha256sum checkpoints/needle2.pkl | awk '{print $1}')
printf 'expected=%s\nactual=%s\n' "$expected" "$actual" | tee metrics/checkpoint.sha256
test "$actual" = "$expected"

python3 - <<'PY'
import json, pathlib, shutil
d=shutil.disk_usage('.')
pathlib.Path('metrics/disk-before.json').write_text(json.dumps({'disk_free_bytes_before': d.free})+'\n')
PY

set +e
set -o pipefail
/usr/bin/time -v -o metrics/finetune.time \
  python scripts/run_seeded_finetune.py experiments/needle-realistic-sft/data/train.needle.jsonl \
    --checkpoint checkpoints/needle2.pkl --seed 0 --epochs 1 --batch-size 16 --lr 1e-4 \
    --lora-rank 16 --lora-alpha 32 --max-len 256 --val-split 0.1 \
    --out artifacts/resource-dry-run-adapter.pkl \
  2>&1 | tee logs/finetune.log
rc=${PIPESTATUS[0]}
set -e
printf '%s\n' "$rc" > metrics/finetune.exit-code

python3 - <<'PY'
import json, pathlib, shutil
before=json.loads(pathlib.Path('metrics/disk-before.json').read_text())
d=shutil.disk_usage('.')
before['disk_free_bytes_after']=d.free
pathlib.Path('metrics/disk.json').write_text(json.dumps(before)+'\n')
PY

test -s metrics/finetune.time
test -s metrics/finetune.exit-code
python3 scripts/realistic_sft_resource_receipt.py \
  --time metrics/finetune.time \
  --exit-code metrics/finetune.exit-code \
  --disk metrics/disk.json \
  --token-audit results/token-length-audit.json \
  --train experiments/needle-realistic-sft/data/train.needle.jsonl \
  --checkpoint checkpoints/needle2.pkl \
  --adapter artifacts/resource-dry-run-adapter.pkl \
  --commit "${GITHUB_SHA:-LOCAL}" --run-id "${GITHUB_RUN_ID:-LOCAL}" \
  --output results/resource-receipt.json

python3 - <<'PY'
import json
r=json.load(open('results/resource-receipt.json'))
assert r['disposition'] == 'PASS_RESOURCE_GATE', r
assert r['interpretation_boundary'] == 'resource_measurement_only_not_model_quality_evidence'
PY

exit "$rc"
