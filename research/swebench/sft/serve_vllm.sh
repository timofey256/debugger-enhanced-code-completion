#!/usr/bin/env bash
set -euo pipefail

WORKDIR="${WORKDIR:-/workspace/runtime-sft}"
MODEL="${MODEL:-$WORKDIR/qwen-runtime-merged}"
SERVED_NAME="${SERVED_NAME:-runtime-lora}"
PORT="${PORT:-8000}"
GPU_UTIL="${GPU_UTIL:-0.9}"

cd "$WORKDIR"
export HF_HOME=/workspace/hf-cache

exec vllm serve "$MODEL" \
    --served-model-name "$SERVED_NAME" \
    --enable-auto-tool-choice \
    --tool-call-parser hermes \
    --max-model-len 32768 \
    --gpu-memory-utilization "$GPU_UTIL" \
    --enable-log-requests \
    --port "$PORT"
