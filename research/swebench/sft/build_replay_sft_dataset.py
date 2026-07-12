#!/usr/bin/env python
"""
Deterministic replay exporter for runtime-tool SFT.

This script takes the benchmark output and extract tool calls and final apply_patch with a
reference patch. Then, it populates each tool call result with the actualy result based on the
repo source code checkout. This is later fed to the model to teach it to read the output of tool calls.

How to run:

python research/swebench/sft/build_replay_sft_dataset.py --run-dir output/benchmark-runs/<run_id> --out output/sft/<run_id>_replay.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from libs.frames import (
    Frame,
    default_exec_path_pipeline,
    default_traceback_pipeline,
    select_most_informative_trace,
)
from libs.frames.pipeline import default_step_frames_pipeline
from libs.llm.tooling import (
    ProjectPathResolver,
    ProjectToolContext,
    RuntimeToolContext,
    ToolInvocation,
    ToolSessionContext,
    create_with_runtime_catalog,
)

CONTAINER_ROOT = "/testbed"
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")
DEFSCAN_RE = re.compile(r"\b(?:def|class)\s+([A-Za-z_]\w*)")


@dataclass(frozen=True)
class ReplayConfig:
    """Knobs of the replay export: run directory, output path, context sizes and limits."""

    run_dir: Path
    out_path: Path
    context_lines: int = 5
    open_pad: int = 3
    max_tool_output_chars: int = 20000
    max_instances: Optional[int] = None
    include_granular: bool = True


@dataclass(frozen=True)
class HunkTarget:
    """One gold-patch hunk: target file, old-side line range and the enclosing function from the hunk header."""

    path: str
    old_start: int
    old_len: int
    func: Optional[str]


@dataclass(frozen=True)
class PatchTargets:
    """All hunks of the gold patch; tells the planner which files and functions to inspect."""

    hunks: Sequence[HunkTarget]

    def files(self) -> list[str]:
        seen: list[str] = []
        for h in self.hunks:
            if h.path not in seen:
                seen.append(h.path)
        return seen

    def functions(self) -> list[str]:
        out: list[str] = []
        for h in self.hunks:
            if h.func and h.func not in out:
                out.append(h.func)
        return out


class PatchParser:
    """Parses a unified diff into `PatchTargets` (files, old-side ranges, hunk-header functions)."""

    def parse(self, patch_text: str) -> PatchTargets:
        hunks: list[HunkTarget] = []
        current: Optional[str] = None
        for line in patch_text.splitlines():
            if line.startswith("+++ "):
                current = self._strip_prefix(line[4:].strip())
                continue
            m = HUNK_RE.match(line)
            if m and current:
                old_start = int(m.group(1))
                old_len = int(m.group(2)) if m.group(2) else 1
                func = self._scan_func(m.group(5))
                hunks.append(HunkTarget(current, old_start, old_len, func))
        return PatchTargets(hunks)

    @staticmethod
    def _strip_prefix(path: str) -> str:
        for prefix in ("a/", "b/"):
            if path.startswith(prefix):
                return path[len(prefix):]
        return path

    @staticmethod
    def _scan_func(context: str) -> Optional[str]:
        m = DEFSCAN_RE.search(context)
        return m.group(1) if m else None


class TraceBundle:
    """One baseline trace run through the default filtering pipelines, with helper queries over its frames."""

    def __init__(self, trace: Mapping[str, Any]):
        self._trace = trace
        self._frames = self._pipe(default_traceback_pipeline(), trace.get("frames", []))
        self._exec_path = self._pipe(default_exec_path_pipeline(), trace.get("exec_path", []))
        self._step_frames = self._pipe(default_step_frames_pipeline(), trace.get("step_frames", []))

    @property
    def trace(self) -> Mapping[str, Any]:
        return self._trace

    @property
    def frames(self) -> Sequence[Frame]:
        return self._frames

    @property
    def exec_path(self) -> Sequence[Frame]:
        return self._exec_path

    @property
    def step_frames(self) -> Sequence[Frame]:
        return self._step_frames

    def referenced_files(self) -> set[str]:
        files: set[str] = set()
        for group in (self._frames, self._exec_path, self._step_frames):
            for frame in group:
                if frame.file.startswith(CONTAINER_ROOT):
                    files.add(frame.file)
        return files

    def deepest_app_func(self) -> Optional[str]:
        for frame in reversed(self._frames):
            if frame.file.startswith(CONTAINER_ROOT) and not self._is_test(frame.file):
                return frame.func
        return None

    def step_func_names(self) -> set[str]:
        return {frame.func for frame in self._step_frames}

    @staticmethod
    def _is_test(path: str) -> bool:
        name = Path(path).name
        return "/tests/" in path or "/test/" in path or name.startswith("test_")

    @staticmethod
    def _pipe(pipeline, raw: Iterable[Mapping[str, Any]]) -> list[Frame]:
        frames = (Frame.from_raw(d) for d in raw)
        return pipeline.run(f for f in frames if f is not None)


class SourceMapBuilder:
    """Reads referenced container files from the local project checkout into a path -> content map."""

    def __init__(self, project_root: Path):
        self._project_root = project_root

    def build(self, container_paths: Iterable[str]) -> dict[str, str]:
        source_map: dict[str, str] = {}
        for container_path in container_paths:
            local = self._to_local(container_path)
            if local is not None and local.is_file():
                source_map[container_path] = local.read_text(encoding="utf-8", errors="replace")
        return source_map

    def _to_local(self, container_path: str) -> Optional[Path]:
        if container_path == CONTAINER_ROOT:
            return self._project_root
        prefix = CONTAINER_ROOT + "/"
        if container_path.startswith(prefix):
            return self._project_root / container_path[len(prefix):]
        return None


class TrajectoryBuilder:
    """Builds one trajectory: plans tool calls from the gold patch, executes them via the real catalog and assembles the messages."""

    def __init__(self, config: ReplayConfig):
        self._config = config
        self._catalog = create_with_runtime_catalog()
        self._parser = PatchParser()

    def build(
        self,
        instance_id: str,
        prompt: str,
        patch_text: str,
        bundle: TraceBundle,
        project_root: Path,
    ) -> Optional[dict[str, Any]]:
        targets = self._parser.parse(patch_text)
        if not targets.hunks:
            return None

        context, resolver = self.make_context(bundle, project_root, targets.files())
        steps = self._plan(targets, bundle, resolver)
        messages, runtime_tools = self.assemble(prompt, context, steps, patch_text)
        return {
            "instance_id": instance_id,
            "messages": messages,
            "meta": {
                "source": "replay",
                "patched_files": targets.files(),
                "n_frames": len(bundle.frames),
                "n_step_frames": len(bundle.step_frames),
                "exc_type": str(bundle.trace.get("exc_type", "")),
                "runtime_tools": runtime_tools,
                "runtime_grounded": runtime_tools > 0,
            },
        }

    def make_context(
        self,
        bundle: TraceBundle,
        project_root: Path,
        extra_files: Iterable[str] = (),
    ) -> tuple[ToolSessionContext, ProjectPathResolver]:
        resolver = ProjectPathResolver(project_root, CONTAINER_ROOT)
        source_files = bundle.referenced_files() | {
            f"{CONTAINER_ROOT}/{f}" for f in extra_files
        }
        source_map = SourceMapBuilder(project_root).build(source_files)
        project_ctx = ProjectToolContext(
            resolver=resolver,
            source_map=source_map,
            context_size=self._config.context_lines,
        )
        runtime_ctx = RuntimeToolContext(
            frames=bundle.frames,
            execution_path=bundle.exec_path,
            step_frames=bundle.step_frames,
            trace=bundle.trace,
            test_output_path=project_root,
        )
        return ToolSessionContext(project=project_ctx, runtime=runtime_ctx), resolver

    def assemble(
        self,
        prompt: str,
        context: ToolSessionContext,
        steps: Sequence[tuple[str, dict[str, Any]]],
        patch_text: str,
    ) -> tuple[list[dict[str, Any]], int]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_message()},
            {"role": "user", "content": prompt},
        ]
        counter = _IdCounter()
        runtime_tools = 0
        for name, args in steps:
            if self._emit(messages, context, counter, name, args):
                if name in ("get_execution_trace", "get_frames", "get_granular_frames"):
                    runtime_tools += 1
        self._emit(messages, context, counter, "apply_patch", {"patch": patch_text}, keep_empty=True)
        return messages, runtime_tools

    def _plan(
        self,
        targets: PatchTargets,
        bundle: TraceBundle,
        resolver: ProjectPathResolver,
    ) -> list[tuple[str, dict[str, Any]]]:
        steps: list[tuple[str, dict[str, Any]]] = [
            ("get_test_error", {}),
            ("get_execution_trace", {}),
            ("get_frames", {}),
        ]
        if self._config.include_granular:
            func = self._granular_func(targets, bundle)
            if func is not None:
                steps.append(("get_granular_frames", {"function_name": func}))
        for path, start, end in self._open_ranges(targets, resolver):
            steps.append(
                ("open_file", {"path": path, "start_line": start, "end_line": end})
            )
        return steps

    def _granular_func(self, targets: PatchTargets, bundle: TraceBundle) -> Optional[str]:
        available = bundle.step_func_names()
        for func in targets.functions():
            if func in available:
                return func
        deepest = bundle.deepest_app_func()
        if deepest in available:
            return deepest
        return None

    def _open_ranges(
        self, targets: PatchTargets, resolver: ProjectPathResolver
    ) -> list[tuple[str, int, int]]:
        ranges: list[tuple[str, int, int]] = []
        for hunk in targets.hunks:
            container_path = f"{CONTAINER_ROOT}/{hunk.path}"
            try:
                local = resolver.resolve(container_path)
            except ValueError:
                continue
            if not local.is_file():
                continue
            start = max(1, hunk.old_start - self._config.open_pad)
            end = hunk.old_start + hunk.old_len + self._config.open_pad
            ranges.append((container_path, start, end))
        return ranges

    def _emit(
        self,
        messages: list[dict[str, Any]],
        context: ToolSessionContext,
        counter: "_IdCounter",
        name: str,
        args: Mapping[str, Any],
        keep_empty: bool = False,
    ) -> bool:
        result = self._catalog.execute(context, ToolInvocation(name=name, arguments=dict(args)))
        if not keep_empty and (
            result.status not in ("ok",) or self._is_uninformative(name, result.output)
        ):
            return False
        call_id = counter.next()
        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                ],
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": result.to_string(max_chars=self._config.max_tool_output_chars),
            }
        )
        return True

    @staticmethod
    def _is_uninformative(name: str, output: str) -> bool:
        body = output.strip()
        if not body:
            return True
        if name == "get_test_error":
            return body.replace("Type:", "").replace("Message:", "").strip() == ""
        if name == "get_granular_frames":
            return body.startswith("No step frames found")
        return False

    @staticmethod
    def _system_message() -> str:
        names = (
            "print_project_tree, open_file, search_symbol, get_test_error, "
            "get_execution_trace, get_frames, get_granular_frames, "
            "get_variable_change, apply_patch"
        )
        return (
            "You can call the following tools to inspect the project and runtime "
            f"before submitting a fix: {names}. "
            "Issue tool calls to gather evidence. Tool outputs are bounded; "
            "request specific files and line ranges. "
            "When you are ready, call apply_patch with a complete unified git diff "
            "to submit the fix and end the session. You have at most 10 tool turns."
        )


class _IdCounter:
    def __init__(self):
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return f"call_{self._n:02d}"


@dataclass
class ExportStats:
    """Counters of the export run: resolved, exported and per-reason skips."""

    resolved: int = 0
    exported: int = 0
    skipped: dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


class ReplayDatasetExporter:
    """Walks the run index, builds a trajectory for every resolved instance and writes the JSONL dataset."""

    def __init__(self, config: ReplayConfig):
        self._config = config
        self._builder = TrajectoryBuilder(config)

    def run(self) -> ExportStats:
        index = json.loads(
            (self._config.run_dir / "index" / "instance_status_index.json").read_text()
        )
        stats = ExportStats()
        self._config.out_path.parent.mkdir(parents=True, exist_ok=True)
        with self._config.out_path.open("w", encoding="utf-8") as sink:
            for record in index.get("records", []):
                if self._config.max_instances and stats.exported >= self._config.max_instances:
                    break
                variant = record.get("variants", {}).get("with_runtime", {})
                if variant.get("status") != "passed":
                    continue
                stats.resolved += 1
                row = self._build_record(record["instance_id"], stats)
                if row is not None:
                    sink.write(json.dumps(row, ensure_ascii=False) + "\n")
                    stats.exported += 1
        return stats

    def _build_record(self, instance_id: str, stats: ExportStats) -> Optional[dict[str, Any]]:
        run_dir = self._config.run_dir
        artifacts = run_dir / "artifacts" / instance_id
        prompt_path = artifacts / "prompt_with_runtime.txt"
        patch_path = artifacts / "reference_patch.diff"
        trace_path = run_dir / "baseline" / instance_id / "auto_debug.json"
        project_root = run_dir / "with_runtime" / instance_id / "project"

        for needed in (prompt_path, patch_path, trace_path):
            if not needed.is_file():
                stats.skip(f"missing:{needed.name}")
                return None
        if not project_root.is_dir():
            stats.skip("missing:project")
            return None

        traces = json.loads(trace_path.read_text())
        if not isinstance(traces, list) or not traces:
            stats.skip("empty_trace")
            return None

        framework = (run_dir.name and instance_id.split("__")[0]) or "unknown"
        bundle = TraceBundle(select_most_informative_trace(traces))
        row = self._builder.build(
            instance_id=instance_id,
            prompt=prompt_path.read_text(encoding="utf-8", errors="replace"),
            patch_text=patch_path.read_text(encoding="utf-8", errors="replace"),
            bundle=bundle,
            project_root=project_root,
        )
        if row is None:
            stats.skip("unparseable_patch")
            return None
        row["framework"] = framework
        return row


def _parse_args() -> ReplayConfig:
    parser = argparse.ArgumentParser(description="Build Layer-1 replay SFT dataset.")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--context-lines", type=int, default=5)
    parser.add_argument("--max-instances", type=int, default=None)
    parser.add_argument("--no-granular", action="store_true")
    args = parser.parse_args()
    return ReplayConfig(
        run_dir=args.run_dir,
        out_path=args.out,
        context_lines=args.context_lines,
        max_instances=args.max_instances,
        include_granular=not args.no_granular,
    )


def main() -> None:
    config = _parse_args()
    stats = ReplayDatasetExporter(config).run()

    if stats.skipped:
        print("skipped:")
        for reason, count in sorted(stats.skipped.items()):
            print(f"  {reason}: {count}")


if __name__ == "__main__":
    main()
