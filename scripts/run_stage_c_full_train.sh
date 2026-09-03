#!/usr/bin/env bash
set -euo pipefail

: "${EXPERIMENT_SHA:?EXPERIMENT_SHA is required}"
: "${LAUNCHER_SHA:?LAUNCHER_SHA is required}"
: "${ARM_ID:?ARM_ID is required}"
: "${REPLICA_ID:?REPLICA_ID is required}"
case "$ARM_ID" in A|B) ;; *) echo BLOCKED_INVALID_ARM_ID; exit 2;; esac
case "$REPLICA_ID" in R1|R2) ;; *) echo BLOCKED_INVALID_REPLICA_ID; exit 2;; esac

mkdir -p checkpoints artifacts results logs metrics
python -m pip install "cactus-needle[train]==2.0.8" 2>&1 | tee logs/install.log
python3 scripts/validate_realistic_sft_dataset.py
python3 scripts/build_stage_c_dataset.py --write

arm=$(printf '%s' "$ARM_ID" | tr '[:upper:]' '[:lower:]')
for phase in early reduced; do
  python3 scripts/audit_stage_c_token_lengths.py \
    --projection "experiments/needle-stage-c-applicability/data/${phase}.arm-${arm}.train.needle.jsonl" \
    --canonical "experiments/needle-stage-c-applicability/state/${phase}.arm-${arm}.canonical.jsonl" \
    --max-len 512 --output "results/token-audit-${phase}-${ARM_ID}-${REPLICA_ID}.json"
done

python - <<'PY' 2>&1 | tee logs/checkpoint-download.log
from huggingface_hub import hf_hub_download
print(hf_hub_download('Cactus-Compute/needle2','checkpoints/needle2.pkl',repo_type='model',local_dir='.'))
PY
checkpoint_expected=4b0a972d163ffc7678fb3c36bace508114872e9d2ce9e10f225825752d3795bc
checkpoint_actual=$(sha256sum checkpoints/needle2.pkl | awk '{print $1}')
test "$checkpoint_actual" = "$checkpoint_expected"

early_adapter="artifacts/early-${ARM_ID}-${REPLICA_ID}.pkl"
final_adapter="artifacts/final-${ARM_ID}-${REPLICA_ID}.pkl"
/usr/bin/time -v -o metrics/train.time \
  python3 scripts/run_stage_c_curriculum_finetune.py \
    --early-jsonl "experiments/needle-stage-c-applicability/data/early.arm-${arm}.train.needle.jsonl" \
    --reduced-jsonl "experiments/needle-stage-c-applicability/data/reduced.arm-${arm}.train.needle.jsonl" \
    --policy experiments/needle-stage-c-applicability/contract/curriculum-policy.json \
    --checkpoint checkpoints/needle2.pkl --seed 0 --epochs 15 --batch-size 16 --lr 1e-4 \
    --lora-rank 16 --lora-alpha 32 --max-len 512 --val-split 0.1 \
    --early-out "$early_adapter" --out "$final_adapter" 2>&1 | tee logs/train.log

early_cact="artifacts/early-${ARM_ID}-${REPLICA_ID}.cact"
final_cact="artifacts/final-${ARM_ID}-${REPLICA_ID}.cact"
needle build checkpoints/needle2.pkl --lora "$early_adapter" --out "$early_cact" 2>&1 | tee logs/build-early.log
needle build checkpoints/needle2.pkl --lora "$final_adapter" --out "$final_cact" 2>&1 | tee logs/build-final.log
python3 scripts/stage_c_train_receipt.py \
  --arm-id "$ARM_ID" --replica-id "$REPLICA_ID" --experiment-commit "$EXPERIMENT_SHA" \
  --launcher-commit "$LAUNCHER_SHA" --run-id "${GITHUB_RUN_ID:-LOCAL}" \
  --early-adapter "$early_adapter" --early-cact "$early_cact" \
  --final-adapter "$final_adapter" --final-cact "$final_cact" \
  --curriculum-manifest experiments/needle-stage-c-applicability/manifests/stage-c-curriculum-manifest.json \
  --output "results/train-receipt-${ARM_ID}-${REPLICA_ID}.json"
sha256sum artifacts/* > results/artifact-sha256.txt
