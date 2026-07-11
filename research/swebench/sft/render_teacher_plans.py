#!/usr/bin/env python
"""
Renders tool-use plans.

Reads plan files and renders each into a trajectory whose tool observations come.


Run from the repository root:

python research/swebench/sft/render_teacher_plans.py \
    --run-dir output/benchmark-runs/<run_id> \
    --plans-dir output/sft/<run_id>_plans \
    --out output/sft/<run_id>_teacher.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional

from build_replay_sft_dataset import (
    PatchParser,
    ReplayConfig,
    TraceBundle,
    TrajectoryBuilder,
)
from libs.frames import select_most_informative_trace

ALLOWED_TOOLS = {
    "print_project_tree",
    "open_file",
    "search_symbol",
    "get_test_error",
    "get_execution_trace",
    "get_frames",
    "get_granular_frames",
}


class TeacherPlanRenderer:
    def __init__(self, config: ReplayConfig, plans_dir: Path):
        self._config = config
        self._plans_dir = plans_dir
        self._builder = TrajectoryBuilder(config)
        self._parser = PatchParser()

    def run(self) -> dict[str, int]:
        stats = {"plans": 0, "rendered": 0, "skipped": 0, "dropped_steps": 0}
        self._config.out_path.parent.mkdir(parents=True, exist_ok=True)
        with self._config.out_path.open("w", encoding="utf-8") as sink:
            for plan_path in sorted(self._plans_dir.glob("*.json")):
                if plan_path.stem.startswith("_"):
                    continue
                stats["plans"] += 1
                row = self._render(plan_path, stats)
                if row is None:
                    stats["skipped"] += 1
                    continue
                sink.write(json.dumps(row, ensure_ascii=False) + "\n")
                stats["rendered"] += 1
        return stats

    def _render(self, plan_path: Path, stats: dict[str, int]) -> Optional[dict[str, Any]]:
        plan_doc = json.loads(plan_path.read_text())
        instance_id = plan_doc.get("instance_id") or plan_path.stem.split("__v")[0]
        variant = plan_doc.get("variant", plan_path.stem)
        steps = self._clean_steps(plan_doc.get("plan", []), stats)
        if not steps:
            return None

        run_dir = self._config.run_dir
        prompt_path = run_dir / "artifacts" / instance_id / "prompt_with_runtime.txt"
        patch_path = run_dir / "artifacts" / instance_id / "reference_patch.diff"
        trace_path = run_dir / "baseline" / instance_id / "auto_debug.json"
        project_root = run_dir / "with_runtime" / instance_id / "project"
        if not (prompt_path.is_file() and patch_path.is_file() and trace_path.is_file()):
            return None
        if not project_root.is_dir():
            return None
        traces = json.loads(trace_path.read_text())
        if not isinstance(traces, list) or not traces:
            return None

        patch_text = patch_path.read_text(encoding="utf-8", errors="replace")
        targets = self._parser.parse(patch_text)
        bundle = TraceBundle(select_most_informative_trace(traces))
        context, _ = self._builder.make_context(bundle, project_root, targets.files())
        messages, runtime_tools = self._builder.assemble(
            prompt_path.read_text(encoding="utf-8", errors="replace"),
            context,
            steps,
            patch_text,
        )
        rendered_calls = sum(1 for m in messages if m["role"] == "assistant") - 1
        stats["dropped_steps"] += max(0, len(steps) - rendered_calls)
        return {
            "instance_id": instance_id,
            "framework": instance_id.split("__")[0],
            "messages": messages,
            "meta": {
                "source": "teacher",
                "variant": variant,
                "patched_files": targets.files(),
                "n_frames": len(bundle.frames),
                "n_step_frames": len(bundle.step_frames),
                "exc_type": str(bundle.trace.get("exc_type", "")),
                "runtime_tools": runtime_tools,
                "runtime_grounded": runtime_tools > 0,
                "plan_steps": len(steps),
            },
        }

    @staticmethod
    def _clean_steps(raw_plan: Any, stats: dict[str, int]) -> list[tuple[str, dict]]:
        steps: list[tuple[str, dict]] = []
        if not isinstance(raw_plan, list):
            return steps
        for entry in raw_plan:
            if not isinstance(entry, dict):
                continue
            name = entry.get("tool")
            args = entry.get("args", {})
            if name not in ALLOWED_TOOLS or not isinstance(args, dict):
                stats["dropped_steps"] += 1
                continue
            steps.append((name, args))
        return steps


def _parse_args() -> tuple[ReplayConfig, Path]:
    parser = argparse.ArgumentParser(description="Render teacher plans into trajectories.")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--plans-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--context-lines", type=int, default=5)
    args = parser.parse_args()
    config = ReplayConfig(
        run_dir=args.run_dir,
        out_path=args.out,
        context_lines=args.context_lines,
    )
    return config, args.plans_dir


def main() -> None:
    config, plans_dir = _parse_args()
    stats = TeacherPlanRenderer(config, plans_dir).run()


if __name__ == "__main__":
    main()
