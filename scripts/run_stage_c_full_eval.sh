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
heldout="experiments/needle-realistic-sft/data/heldout.eval.jsonl"
early="$TRAIN_ARTIFACT_DIR/artifacts/early-${ARM_ID}-${REPLICA_ID}.cact"
final="$TRAIN_ARTIFACT_DIR/artifacts/final-${ARM_ID}-${REPLICA_ID}.cact"
test -s "$early"
test -s "$final"
train_receipt="$TRAIN_ARTIFACT_DIR/results/train-receipt-${ARM_ID}-${REPLICA_ID}.json"
test -s "$train_receipt"
cp "$train_receipt" "results/train-receipt-${ARM_ID}-${REPLICA_ID}.json"
python3 scripts/run_realistic_sft_eval.py --projection "$heldout" --semantic "$semantic" --split heldout --model-id "stage-c-${ARM_ID}-${REPLICA_ID}-early" --weights "$early" --output "results/${ARM_ID}-early-heldout-${REPLICA_ID}.jsonl"
python3 scripts/run_realistic_sft_eval.py --projection "$heldout" --semantic "$semantic" --split heldout --model-id "stage-c-${ARM_ID}-${REPLICA_ID}-final" --weights "$final" --output "results/${ARM_ID}-final-heldout-${REPLICA_ID}.jsonl"
