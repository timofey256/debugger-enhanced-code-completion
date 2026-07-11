# Fine-tuning pipeline (SFT of Qwen2.5-Coder-7B-Instruct)

Scripts in this folder implement the fine-tuning setup.
The resulting model is published at [tymofii256/qwen2.5-coder-7b-ft-runtime](https://huggingface.co/tymofii256/qwen2.5-coder-7b-ft-runtime).

#### Pipeline

The whole pipeline can be visualized as:

```
benchmark run (outputs from benchmark run)
    │
    ├─ 1. build_replay_sft_dataset.py   ── replay of successful runs ──► replay.jsonl
    ├─ 2. dump_teacher_packets.py       ── per-instance evidence packets for the teacher
    │  3. (teacher authors plan JSONs: ordered lists of tool calls)
    │  4. render_teacher_plans.py       ── executes plans against real tools ──► teacher.jsonl
    ├─ 5. validate_sft_dataset.py       ── rejection sampling / quality gates on merged train.jsonl
    ├─ 6. tokenize_trajectories.py      ── ChatML + assistant-only labels ──► HF dataset
    ├─ 7. train_sft.py                  ── LoRA SFT ──► adapter
    └─ 8. serve_vllm.sh                 ── OpenAI-compatible endpoint for harness evaluation
```

#### Description of files

- `requirements_sft.txt` : dependencies.

- `build_replay_sft_dataset.py` : Replays every resolved benchmark instance into an trajectory ending in the gold `apply_patch` (only with tool calls).

- `dump_teacher_packets.py` : Writes a per-instance JSON packet (prompt, evidence-tool outputs, gold patch) with everything a teacher needs to author a tool-use plan.

- `render_teacher_plans.py` : Gets the authored plans and executes them against a real repo and tool catalog.

- `validate_sft_dataset.py` : Applies the rejection-sampling to the rendered dataset (essentially validation step for generated trajectories).

- `tokenize_trajectories.py` : Renders trajectories into Qwen ChatML with the tool schema and masks all non-assistant tokens to -100. Drops trajectories longer than the maximum sequence length.

- `train_sft.py` : LoRA SFT of the base model on the tokenized dataset, with `embed_tokens`/`lm_head` trained alongside the adapters. Hyperparameters are listed in the thesis.

- `remote_train.sh` : Launcher for the training box: installs deps, tokenizes, and starts training in the background.

- `serve_vllm.sh` : Serves the fine-tuned model on vLLM endpoint.
