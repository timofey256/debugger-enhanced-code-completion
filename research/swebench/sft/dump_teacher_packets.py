#!/usr/bin/env python
"""
Dump per-instance teacher packets for Layer-2 trajectory authoring.

For every eligible instance (populated baseline trace + reference patch +
project checkout) writes a compact JSON packet containing the runtime evidence a
teacher needs to author a realistic tool-use plan: the prompt, the rendered
no-arg evidence-tool outputs, the granular functions available, the gold patch,
and the on-disk project root. Plans authored against these packets are rendered
into faithful trajectories by render_teacher_plans.py.

Run from the repository root:

    python research/swebench/sft/dump_teacher_packets.py \
        --run-dir output/benchmark-runs/<run_id> \
        --out-dir output/sft/<run_id>_packets
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional

from build_replay_sft_dataset import (
    CONTAINER_ROOT,
    PatchParser,
    ReplayConfig,
    TraceBundle,
    TrajectoryBuilder,
)
from libs.frames import select_most_informative_trace
from libs.llm.tooling import ToolInvocation, create_with_runtime_catalog


class PacketDumper:
    def __init__(self, run_dir: Path, out_dir: Path, evidence_chars: int = 6000):
        self._run_dir = run_dir
        self._out_dir = out_dir
        self._evidence_chars = evidence_chars
        self._catalog = create_with_runtime_catalog()
        self._builder = TrajectoryBuilder(ReplayConfig(run_dir=run_dir, out_path=out_dir))
        self._parser = PatchParser()

    def run(self) -> list[str]:
        index = json.loads(
            (self._run_dir / "index" / "instance_status_index.json").read_text()
        )
        self._out_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        manifest: list[dict[str, Any]] = []
        for record in index.get("records", []):
            instance_id = record["instance_id"]
            packet = self._build_packet(instance_id, record)
            if packet is None:
                continue
            path = self._out_dir / f"{instance_id}.json"
            path.write_text(json.dumps(packet, ensure_ascii=False, indent=2))
            written.append(instance_id)
            manifest.append(
                {
                    "instance_id": instance_id,
                    "framework": packet["framework"],
                    "status": record.get("variants", {}).get("with_runtime", {}).get("status"),
                    "n_granular_funcs": len(packet["available_granular_funcs"]),
                    "patched_files": packet["patched_files"],
                }
            )
        (self._out_dir / "_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2)
        )
        return written

    def _build_packet(self, instance_id: str, record: dict) -> Optional[dict[str, Any]]:
        artifacts = self._run_dir / "artifacts" / instance_id
        prompt_path = artifacts / "prompt_with_runtime.txt"
        patch_path = artifacts / "reference_patch.diff"
        trace_path = self._run_dir / "baseline" / instance_id / "auto_debug.json"
        project_root = self._run_dir / "with_runtime" / instance_id / "project"
        if not (prompt_path.is_file() and patch_path.is_file() and trace_path.is_file()):
            return None
        if not project_root.is_dir():
            return None
        try:
            traces = json.loads(trace_path.read_text())
        except json.JSONDecodeError:
            return None
        if not isinstance(traces, list) or not traces:
            return None

        patch_text = patch_path.read_text(encoding="utf-8", errors="replace")
        targets = self._parser.parse(patch_text)
        if not targets.hunks:
            return None

        bundle = TraceBundle(select_most_informative_trace(traces))
        context, _ = self._builder.make_context(bundle, project_root, targets.files())

        return {
            "instance_id": instance_id,
            "framework": instance_id.split("__")[0],
            "status": record.get("variants", {}).get("with_runtime", {}).get("status"),
            "project_root": str(project_root.resolve()),
            "container_root": CONTAINER_ROOT,
            "prompt": prompt_path.read_text(encoding="utf-8", errors="replace"),
            "evidence": {
                "get_test_error": self._render(context, "get_test_error", {}),
                "get_execution_trace": self._render(context, "get_execution_trace", {}),
                "get_frames": self._render(context, "get_frames", {}),
            },
            "available_granular_funcs": self._granular_funcs(bundle),
            "patched_files": targets.files(),
            "gold_patch": patch_text,
        }

    def _granular_funcs(self, bundle: TraceBundle) -> list[str]:
        funcs = {
            frame.func
            for frame in bundle.step_frames
            if frame.file.startswith(CONTAINER_ROOT)
        }
        return sorted(funcs)

    def _render(self, context, name: str, args: dict) -> str:
        result = self._catalog.execute(context, ToolInvocation(name=name, arguments=args))
        body = result.output.strip()
        if len(body) > self._evidence_chars:
            body = body[: self._evidence_chars] + "\n... [truncated]"
        return body


def _parse_args():
    parser = argparse.ArgumentParser(description="Dump teacher packets.")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--only", nargs="*", default=None)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    dumper = PacketDumper(args.run_dir, args.out_dir)
    written = dumper.run()
    if args.only:
        keep = set(args.only)
        for path in args.out_dir.glob("*.json"):
            if path.stem != "_manifest" and path.stem not in keep:
                path.unlink()
        written = [w for w in written if w in keep]
    print(f"packets written: {len(written)}")
    print(f"out-dir        : {args.out_dir}")


if __name__ == "__main__":
    main()
