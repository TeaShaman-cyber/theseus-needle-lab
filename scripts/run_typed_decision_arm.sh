#!/usr/bin/env bash
set -euo pipefail

candidate=${1:?candidate required}
out=${2:?output directory required}
mkdir -p "$out"
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

clone_exact() {
  local repo=$1 sha=$2 dest=$3
  rm -rf "$dest"; git init -q "$dest"; git -C "$dest" remote add origin "https://github.com/$repo.git"
  git -C "$dest" fetch -q --depth 1 origin "$sha"; git -C "$dest" checkout -q --detach FETCH_HEAD
  test "$(git -C "$dest" rev-parse HEAD)" = "$sha"
}

case "$candidate" in
  baseline_constant_unknown)
    SETUP_MS=0 python3 scripts/run_typed_decision_candidate.py --candidate "$candidate" --out-dir "$out"
    ;;
  needle3_base)
    start_ms=$(date +%s%3N)
    mkdir -p "$out/setup" "$out/checkpoints"
    python3 -m pip download --no-deps --only-binary=:all: cactus-needle==3.0.4 -d "$out/setup"
    python3 scripts/needle3_deployment_canary.py verify-wheel --wheel "$out/setup/cactus_needle-3.0.4-py3-none-any.whl"
    python3 -m pip install --only-binary=:all: --require-hashes -r experiments/needle3-deployment-canary/v1/requirements.lock.txt
    needle download needle3.safetensors --out "$out"
    python3 scripts/needle3_deployment_canary.py verify-base-checkpoint --checkpoint "$out/checkpoints/needle3.safetensors" --output "$out/setup/base-checkpoint-identity.json"
    end_ms=$(date +%s%3N); export SETUP_MS=$((end_ms-start_ms))
    python3 scripts/run_typed_decision_candidate.py --candidate "$candidate" --checkpoint "$out/checkpoints/needle3.safetensors" --out-dir "$out"
    ;;
  kev_0_8b)
    start_ms=$(date +%s%3N); mkdir -p "$out/setup" .shared
    clone_exact TeaShaman-cyber/theseus-typed-decision-lab 1c8f2fa9f912b27d11471c77cc523493a6359288 .shared/typed-decision-lab
    expected=$(jq -r '.candidates.kev_0_8b.runtime_identity.requirements_sha256' experiments/typed-decision-benchmark/v1/candidates.json)
    observed=$(sha256sum .shared/typed-decision-lab/requirements/kev-cpu-runtime.txt | awk '{print $1}'); test "$observed" = "$expected"
    python3 -m pip install --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple -r .shared/typed-decision-lab/requirements/kev-cpu-runtime.txt
    python3 -m pip install --no-deps "kev @ git+https://github.com/jaredpalmer/kev.git@7405b72e73e2d24787f3720d162a21c974ff2ad2"
    python3 -m pip freeze | sort > "$out/setup/pip-freeze.txt"
    end_ms=$(date +%s%3N); export SETUP_MS=$((end_ms-start_ms))
    python3 scripts/run_typed_decision_candidate.py --candidate "$candidate" --kev-checkpoint "jaredpalmer/kev-0.8b@54f4f8777356cd5bbbb6c6919c657f26e6f2f6d8" --threads 4 --out-dir "$out"
    ;;
  semif_qwen3_0_6b_q8)
    start_ms=$(date +%s%3N); mkdir -p "$out/setup" "$out/model" .shared
    export SEMIF_MODEL_DIR="$out/model"
    clone_exact TeaShaman-cyber/marcopolo-cookbook 821e1cf04dfdfa42ada18255677175203bbab7df .shared/marcopolo-cookbook
    python3 scripts/prepare_semif_release_runtime.py --cookbook-root .shared/marcopolo-cookbook --archive "$RUNNER_TEMP/semif-cpu-toolchain.tar.gz" --checksum-file "$RUNNER_TEMP/semif-cpu-toolchain.tar.gz.sha256" --runtime-dir "$RUNNER_TEMP/semif-runtime" --out "$out/setup/runtime-package-receipt.json"
    export PYTHONPATH="$RUNNER_TEMP/semif-runtime/site-packages${PYTHONPATH:+:$PYTHONPATH}"
    python3 - <<'PY'
import os
from huggingface_hub import hf_hub_download
hf_hub_download(repo_id='Qwen/Qwen3-0.6B-GGUF',filename='Qwen3-0.6B-Q8_0.gguf',revision='23749fefcc72300e3a2ad315e1317431b06b590a',local_dir=os.environ['SEMIF_MODEL_DIR'])
PY
    test "$(sha256sum "$out/model/Qwen3-0.6B-Q8_0.gguf" | awk '{print $1}')" = "9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031"
    python3 scripts/typed_decision_benchmark.py prepare-semif --out "$out/setup/semif-input.jsonl"
    end_ms=$(date +%s%3N); export SETUP_MS=$((end_ms-start_ms))
    python3 -m semif_phase1.cli --mode direct --backend llamacpp --model Qwen/Qwen3-0.6B --revision c1899de289a04d12100db370d81485cdf75e47ca --gguf "$out/model/Qwen3-0.6B-Q8_0.gguf" --llama-threads 4 --max-tokens 2048 --input "$out/setup/semif-input.jsonl" --output "$out/setup/semif-output.jsonl"
    python3 scripts/finalize_typed_decision_semif.py --native-input "$out/setup/semif-input.jsonl" --native-output "$out/setup/semif-output.jsonl" --runtime-package-receipt "$out/setup/runtime-package-receipt.json" --gguf "$out/model/Qwen3-0.6B-Q8_0.gguf" --out-dir "$out"
    ;;
  *) echo "unknown candidate: $candidate" >&2; exit 2;;
esac
