#!/usr/bin/env python
"""
Tokenize SFT trajectories into Qwen2.5-Coder ChatML with assistant-only loss.

Read a JSONL of trajectories, renders them with the model's chat template plus the
runtime tool schema, and computes per-token labels that supervise ONLY the
assistant tool-call tokens (role headers, prompts, and tool observations are
masked with -100). Splits by instance_id to avoid variant leakage and saves a
HuggingFace dataset to disk.


Run using:

python tokenize_trajectories.py \
    --dataset data/datasets/train.jsonl \
    --tools data/datasets/tools_schema.json \
    --model Qwen/Qwen2.5-Coder-7B-Instruct \
    --out output/sft/tokenized \
    --max-len 10240 --val-instances 16
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from datasets import Dataset, DatasetDict
from transformers import AutoTokenizer


@dataclass(frozen=True)
class TokenizeConfig:
    dataset_path: Path
    tools_path: Optional[Path]
    model_name: str
    out_dir: Path
    max_len: int
    val_instances: int
    seed: int
    use_tools: bool


class TrajectoryTokenizer:
    def __init__(self, config: TokenizeConfig):
        self._config = config
        self._tokenizer = AutoTokenizer.from_pretrained(config.model_name, trust_remote_code=True)
        self._tools = self._load_tools()

    def _load_tools(self) -> Optional[list[dict[str, Any]]]:
        if not self._config.use_tools or self._config.tools_path is None:
            return None
        return json.loads(self._config.tools_path.read_text())

    def _render_len(self, messages: list[dict[str, Any]], add_generation_prompt: bool) -> list[int]:
        return self._tokenizer.apply_chat_template(
            messages,
            tools=self._tools,
            add_generation_prompt=add_generation_prompt,
            tokenize=True,
        )

    def encode(self, messages: list[dict[str, Any]]) -> Optional[dict[str, list[int]]]:
        normalized = [self._normalize(m) for m in messages]
        input_ids = self._render_len(normalized, add_generation_prompt=False)
        labels = [-100] * len(input_ids)

        prefix_cache: dict[int, list[int]] = {0: []}
        for k in range(1, len(normalized) + 1):
            prefix_cache[k] = self._render_len(normalized[:k], False)

        for k, message in enumerate(normalized):
            if message.get("role") != "assistant":
                continue
            before = prefix_cache[k]
            after = prefix_cache[k + 1]
            if not self._is_prefix(before, after):
                return None
            header = self._render_len(normalized[:k], add_generation_prompt=True)
            if not self._is_prefix(before, header) or len(header) > len(after):
                return None
            for idx in range(len(header), len(after)):
                labels[idx] = input_ids[idx]

        if not any(label != -100 for label in labels):
            return None
        if len(input_ids) > self._config.max_len:
            return None
        return {
            "input_ids": input_ids,
            "labels": labels,
            "attention_mask": [1] * len(input_ids),
        }

    @staticmethod
    def _normalize(message: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {"role": message["role"], "content": message.get("content", "") or ""}
        if message.get("tool_calls"):
            out["tool_calls"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": TrajectoryTokenizer._as_object(tc["function"]["arguments"]),
                    },
                }
                for tc in message["tool_calls"]
            ]
            out["content"] = message.get("content", "") or ""
        if message["role"] == "tool" and message.get("name"):
            out["name"] = message["name"]
        return out

    @staticmethod
    def _as_object(arguments: Any) -> Any:
        if isinstance(arguments, str):
            try:
                return json.loads(arguments)
            except json.JSONDecodeError:
                return arguments
        return arguments

    @staticmethod
    def _is_prefix(short: list[int], long: list[int]) -> bool:
        return len(short) <= len(long) and short == long[: len(short)]


class TokenizedDatasetBuilder:
    def __init__(self, config: TokenizeConfig):
        self._config = config
        self._encoder = TrajectoryTokenizer(config)

    def build(self) -> DatasetDict:
        rows = [json.loads(line) for line in self._config.dataset_path.open()]
        val_ids = self._select_val_instances(rows)

        train_records: list[dict[str, Any]] = []
        val_records: list[dict[str, Any]] = []
        skipped = 0
        lengths: list[int] = []
        for row in rows:
            encoded = self._encoder.encode(row["messages"])
            if encoded is None:
                skipped += 1
                continue
            lengths.append(len(encoded["input_ids"]))
            target = val_records if row["instance_id"] in val_ids else train_records
            target.append(encoded)

        self._report(train_records, val_records, skipped, lengths)
        dataset = DatasetDict(
            train=Dataset.from_list(train_records),
            validation=Dataset.from_list(val_records),
        )
        dataset.save_to_disk(str(self._config.out_dir))
        return dataset

    def _select_val_instances(self, rows: list[dict[str, Any]]) -> set[str]:
        if self._config.val_instances <= 0:
            return set()
        instances = sorted({row["instance_id"] for row in rows})
        rng = random.Random(self._config.seed)
        rng.shuffle(instances)
        return set(instances[: self._config.val_instances])

    def _report(
        self,
        train_records: list[dict[str, Any]],
        val_records: list[dict[str, Any]],
        skipped: int,
        lengths: list[int],
    ) -> None:
        print(f"model            : {self._config.model_name}")
        print(f"tools in prompt  : {self._config.use_tools}")
        print(f"train trajectories: {len(train_records)}")
        print(f"val trajectories : {len(val_records)}")
        print(f"skipped (len>{self._config.max_len} or unmaskable): {skipped}")
        if lengths:
            ordered = sorted(lengths)
            print(
                "token length min/median/p95/max: "
                f"{ordered[0]}/{ordered[len(ordered)//2]}/"
                f"{ordered[int(len(ordered)*0.95)]}/{ordered[-1]}"
            )
        print(f"saved to         : {self._config.out_dir}")


def _parse_args() -> TokenizeConfig:
    parser = argparse.ArgumentParser(description="Tokenize SFT trajectories.")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--tools", type=Path, default=None)
    parser.add_argument("--model", default="Qwen/Qwen2.5-Coder-7B-Instruct")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--max-len", type=int, default=10240)
    parser.add_argument("--val-instances", type=int, default=16)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--no-tools", action="store_true")
    args = parser.parse_args()
    return TokenizeConfig(
        dataset_path=args.dataset,
        tools_path=args.tools,
        model_name=args.model,
        out_dir=args.out,
        max_len=args.max_len,
        val_instances=args.val_instances,
        seed=args.seed,
        use_tools=not args.no_tools,
    )


def main() -> None:
    TokenizedDatasetBuilder(_parse_args()).build()


if __name__ == "__main__":
    main()
