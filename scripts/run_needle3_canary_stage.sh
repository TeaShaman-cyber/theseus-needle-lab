#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: run_needle3_canary_stage.sh STAGE [--artifact-root PATH] [--track PATH] -- COMMAND..." >&2
  exit 2
fi

stage=$1
shift
artifact_args=()
track_args=()

while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do
  case "$1" in
    --artifact-root)
      [ "$#" -ge 2 ] || { echo "missing --artifact-root value" >&2; exit 2; }
      artifact_args+=(--artifact-root "$2")
      shift 2
      ;;
    --track)
      [ "$#" -ge 2 ] || { echo "missing --track value" >&2; exit 2; }
      track_args+=(--track "$2")
      shift 2
      ;;
    *)
      echo "unknown stage wrapper option: $1" >&2
      exit 2
      ;;
  esac
done

[ "$#" -gt 0 ] && [ "$1" = "--" ] || { echo "missing -- command delimiter" >&2; exit 2; }
shift
[ "$#" -gt 0 ] || { echo "missing stage command" >&2; exit 2; }

: "${EXPERIMENT_SHA:?EXPERIMENT_SHA required}"
: "${LAUNCHER_SHA:?LAUNCHER_SHA required}"
: "${GITHUB_RUN_ID:?GITHUB_RUN_ID required}"
: "${GITHUB_RUN_ATTEMPT:?GITHUB_RUN_ATTEMPT required}"

case "$EXPERIMENT_SHA" in
  *[!0-9a-f]*|"") echo "invalid EXPERIMENT_SHA" >&2; exit 2 ;;
esac
case "$LAUNCHER_SHA" in
  *[!0-9a-f]*|"") echo "invalid LAUNCHER_SHA" >&2; exit 2 ;;
esac
[ "${#EXPERIMENT_SHA}" -eq 40 ] || { echo "invalid EXPERIMENT_SHA length" >&2; exit 2; }
[ "${#LAUNCHER_SHA}" -eq 40 ] || { echo "invalid LAUNCHER_SHA length" >&2; exit 2; }

mkdir -p "_evidence/telemetry/$stage" "_evidence/diagnostics"

exec python3 scripts/execution_telemetry.py run \
  --experiment-sha "$EXPERIMENT_SHA" \
  --launcher-sha "$LAUNCHER_SHA" \
  --run-id "$GITHUB_RUN_ID" \
  --run-attempt "$GITHUB_RUN_ATTEMPT" \
  --stage "$stage" \
  --unit canary \
  --heartbeat-seconds 300 \
  --checkpoint "_evidence/telemetry/$stage/checkpoint.json" \
  --heartbeat "_evidence/telemetry/$stage/heartbeat.jsonl" \
  "${artifact_args[@]}" \
  -- python3 scripts/needle3_stage_diagnostics.py \
    --stage "$stage" \
    --summary "_evidence/diagnostics/$stage.json" \
    --interval-seconds 60 \
    "${track_args[@]}" \
    -- "$@"
