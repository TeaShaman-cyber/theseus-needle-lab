#!/usr/bin/env bash
set -euo pipefail
: "${EXPERIMENT_SHA:?EXPERIMENT_SHA is required}"
: "${LAUNCHER_SHA:?LAUNCHER_SHA is required}"
: "${ARM_ID:?ARM_ID is required}"
: "${REPLICA_ID:?REPLICA_ID is required}"
: "${TRAIN_ARTIFACT_DIR:?TRAIN_ARTIFACT_DIR is required}"
case "$ARM_ID" in A|B) ;; *) echo BLOCKED_INVALID_ARM_ID; exit 2;; esac
case "$REPLICA_ID" in R1|R2) ;; *) echo BLOCKED_INVALID_REPLICA_ID; exit 2;; esac

mkdir -p results logs
python -m pip install "cactus-needle==2.0.8" 2>&1 | tee logs/eval-install.log
python3 scripts/validate_realistic_sft_dataset.py
semantic="experiments/needle-realistic-sft/source/semantic-cases.jsonl"
route_schema="experiments/needle-realistic-sft/contract/route-schema.json"
prefix="experiments/needle-realistic-sft/contract/route-positive-prefix.txt"
early="$TRAIN_ARTIFACT_DIR/artifacts/early-${ARM_ID}-${REPLICA_ID}.cact"
final="$TRAIN_ARTIFACT_DIR/artifacts/final-${ARM_ID}-${REPLICA_ID}.cact"
test -s "$early"
test -s "$final"
train_receipt="$TRAIN_ARTIFACT_DIR/results/train-receipt-${ARM_ID}-${REPLICA_ID}.json"
test -s "$train_receipt"
expected_early=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["artifacts"]["early_cact_sha256"])' "$train_receipt")
expected_final=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["artifacts"]["final_cact_sha256"])' "$train_receipt")
actual_early=$(sha256sum "$early" | awk '{print $1}')
actual_final=$(sha256sum "$final" | awk '{print $1}')
if [[ "$actual_early" != "$expected_early" || "$actual_final" != "$expected_final" ]]; then
  echo MODEL_ARTIFACT_HASH_MISMATCH
  exit 3
fi
cp "$train_receipt" "results/train-receipt-${ARM_ID}-${REPLICA_ID}.json"
python3 scripts/run_stage_c_eval.py --semantic "$semantic" --route-schema "$route_schema" --prefix "$prefix" --split heldout --arm-id "$ARM_ID" --model-id "stage-c-${ARM_ID}-${REPLICA_ID}-early" --weights "$early" --output "results/${ARM_ID}-early-heldout-${REPLICA_ID}.jsonl"
python3 scripts/run_stage_c_eval.py --semantic "$semantic" --route-schema "$route_schema" --prefix "$prefix" --split heldout --arm-id "$ARM_ID" --model-id "stage-c-${ARM_ID}-${REPLICA_ID}-final" --weights "$final" --output "results/${ARM_ID}-final-heldout-${REPLICA_ID}.jsonl"
