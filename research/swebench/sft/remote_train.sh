#!/usr/bin/env bash
set -euo pipefail

WORKDIR="${WORKDIR:-/workspace/runtime-sft}"
MODEL="${MODEL:-Qwen/Qwen2.5-Coder-7B-Instruct}"
MAXLEN="${MAXLEN:-10240}"
EPOCHS="${EPOCHS:-3}"
LR="${LR:-1e-4}"
GRAD_ACCUM="${GRAD_ACCUM:-16}"

cd "$WORKDIR"

echo "=== [1/4] installing deps ==="
pip install -q -r requirements_sft.txt
pip install -q flash-attn --no-build-isolation 2>/dev/null || echo "flash-attn unavailable; falling back to sdpa"

echo "=== [2/4] tokenizing ==="
python tokenize_trajectories.py \
    --dataset train.jsonl \
    --tools tools_schema.json \
    --model "$MODEL" \
    --out tokenized \
    --max-len "$MAXLEN" \
    --val-instances 16

echo "=== [3/4] training (logging to train.log) ==="
nohup python train_sft.py \
    --data tokenized \
    --model "$MODEL" \
    --out qwen-runtime-lora \
    --epochs "$EPOCHS" \
    --lr "$LR" \
    --grad-accum "$GRAD_ACCUM" \
    > train.log 2>&1 &
echo "training PID: $!"
echo "=== [4/4] launched. tail -f $WORKDIR/train.log ==="
