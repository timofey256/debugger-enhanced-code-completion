#!/usr/bin/env python
"""
Main SFT script. The default hyperparams are defined in the thesis.

python train_sft.py \
    --data output/sft/tokenized \
    --model Qwen/Qwen2.5-Coder-7B-Instruct \
    --out output/sft/qwen7b-runtime-lora \
    --epochs 3 --lr 1e-4
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import torch
from datasets import load_from_disk
from peft import LoraConfig, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainingArguments,
)


@dataclass(frozen=True)
class TrainConfig:
    data_dir: Path
    model_name: str
    out_dir: Path
    epochs: float
    lr: float
    per_device_batch: int
    grad_accum: int
    warmup_ratio: float
    lora_r: int
    lora_alpha: int
    lora_dropout: float
    weight_decay: float
    save_steps: int
    logging_steps: int
    target_modules: tuple[str, ...] = field(
        default=(
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        )
    )


class SFTTrainerBuilder:
    def __init__(self, config: TrainConfig):
        self._config = config

    def run(self) -> None:
        tokenizer = AutoTokenizer.from_pretrained(self._config.model_name, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = self._load_model()
        model = get_peft_model(model, self._lora_config())
        model.print_trainable_parameters()

        dataset = load_from_disk(str(self._config.data_dir))
        collator = DataCollatorForSeq2Seq(
            tokenizer,
            model=model,
            label_pad_token_id=-100,
            padding="longest",
        )

        trainer = Trainer(
            model=model,
            args=self._training_args(),
            train_dataset=dataset["train"],
            eval_dataset=dataset["validation"] if len(dataset["validation"]) else None,
            data_collator=collator,
        )
        trainer.train()
        trainer.save_model(str(self._config.out_dir))
        tokenizer.save_pretrained(str(self._config.out_dir))

    def _load_model(self) -> AutoModelForCausalLM:
        attn = "flash_attention_2" if self._flash_available() else "sdpa"
        model = AutoModelForCausalLM.from_pretrained(
            self._config.model_name,
            torch_dtype=torch.bfloat16,
            attn_implementation=attn,
            trust_remote_code=True,
        )
        model.config.use_cache = False
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.enable_input_require_grads()
        return model

    @staticmethod
    def _flash_available() -> bool:
        try:
            import flash_attn  # noqa: F401

            return True
        except ImportError:
            return False

    def _lora_config(self) -> LoraConfig:
        return LoraConfig(
            r=self._config.lora_r,
            lora_alpha=self._config.lora_alpha,
            lora_dropout=self._config.lora_dropout,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=list(self._config.target_modules),
            modules_to_save=["embed_tokens", "lm_head"],
        )

    def _training_args(self) -> TrainingArguments:
        return TrainingArguments(
            output_dir=str(self._config.out_dir),
            num_train_epochs=self._config.epochs,
            per_device_train_batch_size=self._config.per_device_batch,
            per_device_eval_batch_size=1,
            gradient_accumulation_steps=self._config.grad_accum,
            learning_rate=self._config.lr,
            weight_decay=self._config.weight_decay,
            lr_scheduler_type="cosine",
            warmup_ratio=self._config.warmup_ratio,
            bf16=True,
            gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
            logging_steps=self._config.logging_steps,
            save_steps=self._config.save_steps,
            save_total_limit=3,
            eval_strategy="steps",
            eval_steps=self._config.save_steps,
            report_to=[],
            optim="adamw_torch",
            seed=13,
        )


def _parse_args() -> TrainConfig:
    parser = argparse.ArgumentParser(description="LoRA SFT on runtime-tool trajectories.")
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--model", default="Qwen/Qwen2.5-Coder-7B-Instruct")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--per-device-batch", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=16)
    parser.add_argument("--warmup-ratio", type=float, default=0.03)
    parser.add_argument("--lora-r", type=int, default=32)
    parser.add_argument("--lora-alpha", type=int, default=64)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--save-steps", type=int, default=50)
    parser.add_argument("--logging-steps", type=int, default=5)
    args = parser.parse_args()
    return TrainConfig(
        data_dir=args.data,
        model_name=args.model,
        out_dir=args.out,
        epochs=args.epochs,
        lr=args.lr,
        per_device_batch=args.per_device_batch,
        grad_accum=args.grad_accum,
        warmup_ratio=args.warmup_ratio,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        weight_decay=args.weight_decay,
        save_steps=args.save_steps,
        logging_steps=args.logging_steps,
    )


def main() -> None:
    SFTTrainerBuilder(_parse_args()).run()


if __name__ == "__main__":
    main()
