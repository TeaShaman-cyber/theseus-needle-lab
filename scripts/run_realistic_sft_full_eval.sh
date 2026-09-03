#!/usr/bin/env bash
set -euo pipefail
: "${EXPERIMENT_SHA:?EXPERIMENT_SHA is required}"
: "${LAUNCHER_SHA:?LAUNCHER_SHA is required}"
: "${REPLICA_ID:?REPLICA_ID is required}"
: "${TRAIN_ARTIFACT_DIR:?TRAIN_ARTIFACT_DIR is required}"
case "$REPLICA_ID" in R1|R2) ;; *) echo BLOCKED_INVALID_REPLICA_ID; exit 2;; esac

mkdir -p results logs
python -m pip install "cactus-needle==2.0.8" 2>&1 | tee logs/eval-install.log
python3 scripts/validate_realistic_sft_dataset.py

semantic="experiments/needle-realistic-sft/source/semantic-cases.jsonl"
train_projection="experiments/needle-realistic-sft/data/train.needle.jsonl"
heldout_projection="experiments/needle-realistic-sft/data/heldout.eval.jsonl"
cact="$TRAIN_ARTIFACT_DIR/artifacts/tuned-${REPLICA_ID}.cact"
train_receipt="$TRAIN_ARTIFACT_DIR/results/train-receipt-${REPLICA_ID}.json"
test -s "$cact"
test -s "$train_receipt"

python3 scripts/run_realistic_sft_eval.py --projection "$train_projection" --semantic "$semantic" --split train --model-id "base-${REPLICA_ID}" --output "results/base-train-${REPLICA_ID}.jsonl"
python3 scripts/run_realistic_sft_eval.py --projection "$train_projection" --semantic "$semantic" --split train --model-id "tuned-${REPLICA_ID}" --weights "$cact" --output "results/tuned-train-${REPLICA_ID}.jsonl"
python3 scripts/run_realistic_sft_eval.py --projection "$heldout_projection" --semantic "$semantic" --split heldout --model-id "base-${REPLICA_ID}" --output "results/base-heldout-${REPLICA_ID}.jsonl"
python3 scripts/run_realistic_sft_eval.py --projection "$heldout_projection" --semantic "$semantic" --split heldout --model-id "tuned-${REPLICA_ID}" --weights "$cact" --output "results/tuned-heldout-${REPLICA_ID}.jsonl"

python3 scripts/realistic_sft_quality_receipt.py replica \
  --base-train "results/base-train-${REPLICA_ID}.jsonl" \
  --tuned-train "results/tuned-train-${REPLICA_ID}.jsonl" \
  --base-heldout "results/base-heldout-${REPLICA_ID}.jsonl" \
  --tuned-heldout "results/tuned-heldout-${REPLICA_ID}.jsonl" \
  --train-receipt "$train_receipt" --tuned-cact "$cact" \
  --replica-id "$REPLICA_ID" --experiment-commit "$EXPERIMENT_SHA" \
  --launcher-commit "$LAUNCHER_SHA" --run-id "${GITHUB_RUN_ID:-LOCAL}" \
  --output "results/eval-receipt-${REPLICA_ID}.json"
