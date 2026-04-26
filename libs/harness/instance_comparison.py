from __future__ import annotations

import json
import logging
import re
import shlex
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, TypeVar

import docker

from libs.harness.framework_detector import FrameworkDetector
from libs.harness.trace_output import TraceOutputManager
from libs.harness.traced_runner import RunResult, TracedInstanceRunner
from libs.frames import Frame, StdlibFrameFilter

from libs.prompts import PromptBuilder, load_prompt

from swebench.harness.constants import (
    DOCKER_WORKDIR,
    KEY_MODEL,
    KEY_PREDICTION,
    UTF8,
)


class Variant(str, Enum):
    BASELINE = "baseline"
    WITHOUT_RUNTIME = "without_runtime"
    WITH_RUNTIME = "with_runtime"


class Status(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"
    APPLY_FAILED = "apply_failed"
    NOT_RUN = "not_run"


class Verdict(str, Enum):
    FIXED = "fixed"
    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    REGRESSED = "regressed"
    NOT_RUN = "not_run"
    UNKNOWN = "unknown"


T = TypeVar("T")


@dataclass
class Outcome:
    status: Status = Status.UNKNOWN
    failure_count: Optional[int] = None
    ran_tests: Optional[int] = None
    summary_line: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "failure_count": self.failure_count,
            "ran_tests": self.ran_tests,
            "summary_line": self.summary_line,
        }


@dataclass
class VariantResult:
    variant: Variant
    prompt_path: Path
    response_path: Path
    patch_path: Path
    generated_patch: str
    outcome: Outcome
    run_result: RunResult
    run_skipped: bool = False
    test_output_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        run_result_payload: Any = (
            self.run_result.to_dict()
            if hasattr(self.run_result, "to_dict")
            else self.run_result
        )
        payload: Dict[str, Any] = {
            "variant": self.variant.value,
            "prompt_path": str(self.prompt_path),
            "response_path": str(self.response_path),
            "patch_path": str(self.patch_path),
            "generated_patch": self.generated_patch,
            "run_skipped": self.run_skipped,
            "run_result": run_result_payload,
            "outcome": self.outcome.to_dict(),
        }
        if self.test_output_path is not None:
            payload["test_output_path"] = str(self.test_output_path)
        return payload


@dataclass
class ComparisonConfig:
    model_name: str
    max_tokens: int = 2500
    context_lines: int = 8
    test_context_lines: int = 25
    max_context_files: int = 4
    timeout: Optional[int] = None
    force_rebuild: bool = False
    nocache: bool = False


@dataclass
class ComparisonReport:
    instance_id: str
    framework: Optional[str]
    created_at: str
    baseline: Dict[str, Any]
    without_runtime: VariantResult
    with_runtime: VariantResult
    patches: Dict[str, str]
    comparison: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "framework": self.framework,
            "created_at": self.created_at,
            Variant.BASELINE.value: self.baseline,
            Variant.WITHOUT_RUNTIME.value: self.without_runtime.to_dict(),
            Variant.WITH_RUNTIME.value: self.with_runtime.to_dict(),
            "patches": self.patches,
            "comparison": self.comparison,
        }


class _Baseline(NamedTuple):
    run_result: RunResult
    traces: List[Dict[str, Any]]
    test_output_path: Path
    test_output: str
    outcome: Outcome
    file_line_map: Dict[str, List[int]]
    selected_files: List[str]
    source_map: Dict[str, str]


class _Prompts(NamedTuple):
    without: str
    with_: str
    failure_summary: str
    testcase_source: str
    related_context: str


class InstanceComparison:
    def __init__(
        self,
        *,
        test_spec,
        reference_pred: Dict[str, Any],
        client: docker.DockerClient,
        llm,
        trace_collector_dir: Path,
        output_dir: Path,
        run_id: str,
        config: ComparisonConfig,
        logger: logging.Logger,
        framework_detector: Optional[FrameworkDetector] = None,
    ):
        self._test_spec = test_spec
        self._reference_pred = reference_pred
        self._client = client
        self._llm = llm
        self._trace_collector_dir = Path(trace_collector_dir)
        self._output_dir = Path(output_dir)
        self._run_id = run_id
        self._config = config
        self._logger = logger
        self._stdlib_filter = StdlibFrameFilter()
        self._framework_detector = framework_detector or FrameworkDetector()

        self._framework = self._framework_detector.detect(self._test_spec)
        self._framework_value = self._framework.value

        self._baseline_base = self._output_dir / Variant.BASELINE.value
        self._without_base = self._output_dir / Variant.WITHOUT_RUNTIME.value
        self._with_base = self._output_dir / Variant.WITH_RUNTIME.value
        self._artifacts_dir = self._output_dir / "artifacts" / test_spec.instance_id
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)

        self._baseline_output = TraceOutputManager(self._baseline_base)
        self._without_output = TraceOutputManager(self._without_base)
        self._with_output = TraceOutputManager(self._with_base)

        self._baseline_runner = self._make_runner(self._baseline_output, Variant.BASELINE)
        self._without_runner = self._make_runner(self._without_output, Variant.WITHOUT_RUNTIME)
        self._with_runner = self._make_runner(self._with_output, Variant.WITH_RUNTIME)

    def _make_runner(
        self, output_manager: TraceOutputManager, variant: Variant
    ) -> TracedInstanceRunner:
        return TracedInstanceRunner(
            client=self._client,
            test_spec=self._test_spec,
            run_id=f"{self._run_id}_{variant.value}",
            trace_collector_dir=self._trace_collector_dir,
            output_manager=output_manager,
            framework_detector=self._framework_detector,
            logger=self._logger,
            timeout=self._config.timeout,
            force_rebuild=self._config.force_rebuild,
            nocache=self._config.nocache,
        )

    def run(self) -> ComparisonReport:
        instance_id = self._test_spec.instance_id
        self._logger.info("\n%s", "=" * 70)
        self._logger.info("Processing debugger comparison for %s", instance_id)
        self._logger.info("%s", "=" * 70)

        reference_patch = str(self._reference_pred.get(KEY_PREDICTION, ""))
        self._write_text(self._artifacts_dir / "reference_patch.diff", reference_patch)

        baseline = self._collect_baseline()
        prompts = self._build_prompts(baseline)

        without = self._run_variant(
            Variant.WITHOUT_RUNTIME,
            prompts.without,
            self._without_runner,
            self._without_output,
        )
        with_ = self._run_variant(
            Variant.WITH_RUNTIME,
            prompts.with_,
            self._with_runner,
            self._with_output,
        )

        report = self._build_report(baseline, without, with_, reference_patch)

        report_path = self._artifacts_dir / "comparison_report.json"
        self._write_text(
            report_path, json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
        )
        self._logger.info("Saved report: %s", report_path)
        return report

    def _collect_baseline(self) -> _Baseline:
        instance_id = self._test_spec.instance_id
        run_result = self._baseline_runner.run(self._reference_pred, skip_patch=True)

        trace_path = (
            Path(run_result.trace_path)
            if run_result.trace_path
            else self._baseline_output.trace_file(instance_id)
        )
        traces = self._read_json_list(trace_path)

        test_output_path = self._resolve_test_output_path(
            run_result, self._baseline_output, instance_id
        )
        test_output = self._read_text(test_output_path)
        outcome = self._parse_test_output(test_output)

        file_line_map = self._collect_file_line_map(traces)
        selected_files = self._select_context_files(
            file_line_map, self._config.max_context_files
        )
        all_trace_files = list(file_line_map.keys())
        files_to_read = list(dict.fromkeys(selected_files + all_trace_files))
        source_map = self._read_files_from_image(
            self._test_spec.instance_image_key, files_to_read
        )

        return _Baseline(
            run_result=run_result,
            traces=traces,
            test_output_path=test_output_path,
            test_output=test_output,
            outcome=outcome,
            file_line_map=file_line_map,
            selected_files=selected_files,
            source_map=source_map,
        )

    def _build_prompts(self, baseline: _Baseline) -> _Prompts:
        failure_summary = self._summarize_failures(baseline.traces, baseline.test_output)
        testcase_source = self._render_testcase_source(
            baseline.file_line_map,
            baseline.selected_files,
            baseline.source_map,
            self._config.test_context_lines,
        )
        related_context = self._render_related_source_context(
            baseline.selected_files,
            baseline.file_line_map,
            baseline.source_map,
            self._config.context_lines,
        )

        without = self._build_prompt(
            traces=baseline.traces,
            failure_summary=failure_summary,
            testcase_source=testcase_source,
            related_context=related_context,
            include_runtime=False,
            source_map=baseline.source_map,
        )
        with_ = self._build_prompt(
            traces=baseline.traces,
            failure_summary=failure_summary,
            testcase_source=testcase_source,
            related_context=related_context,
            include_runtime=True,
            source_map=baseline.source_map,
        )
        return _Prompts(
            without=without,
            with_=with_,
            failure_summary=failure_summary,
            testcase_source=testcase_source,
            related_context=related_context,
        )

    def _run_variant(
        self,
        variant: Variant,
        prompt: str,
        runner: TracedInstanceRunner,
        output_manager: TraceOutputManager,
    ) -> VariantResult:
        variant_name = variant.value
        prompt_path = self._artifacts_dir / f"prompt_{variant_name}.txt"
        response_path = self._artifacts_dir / f"response_{variant_name}.txt"
        patch_path = self._artifacts_dir / f"patch_{variant_name}.diff"

        self._write_text(prompt_path, prompt)

        response_text = self._llm.complete_code(prompt, max_tokens=self._config.max_tokens)
        self._write_text(response_path, response_text)

        patch_text = self._extract_unified_diff(response_text)
        self._write_text(patch_path, patch_text)

        if not patch_text.strip():
            return VariantResult(
                variant=variant,
                prompt_path=prompt_path,
                response_path=response_path,
                patch_path=patch_path,
                generated_patch=patch_text,
                outcome=Outcome(
                    status=Status.NOT_RUN,
                    summary_line="not run (no patch extracted)",
                ),
                run_result=RunResult(
                    success=False,
                    instance_id=self._test_spec.instance_id,
                    framework=self._framework_value,
                    error="No unified diff could be extracted from model response.",
                ),
                run_skipped=True,
            )

        variant_pred = dict(self._reference_pred)
        variant_pred[KEY_PREDICTION] = patch_text
        variant_pred[KEY_MODEL] = f"{self._config.model_name}-{variant_name}"

        run_result = runner.run(variant_pred, skip_patch=False)
        instance_id = self._test_spec.instance_id

        if not run_result.success:
            run_error = run_result.error or "variant execution failed"
            status = Status.APPLY_FAILED if "Patch Apply Failed" in run_error else Status.NOT_RUN
            return VariantResult(
                variant=variant,
                prompt_path=prompt_path,
                response_path=response_path,
                patch_path=patch_path,
                generated_patch=patch_text,
                outcome=Outcome(status=status, summary_line=run_error),
                run_result=run_result,
                run_skipped=True,
                test_output_path=self._resolve_test_output_path(
                    run_result, output_manager, instance_id
                ),
            )

        test_output_path = self._resolve_test_output_path(
            run_result, output_manager, instance_id
        )
        test_output_text = self._read_text(test_output_path)
        outcome = self._parse_test_output(test_output_text)

        return VariantResult(
            variant=variant,
            prompt_path=prompt_path,
            response_path=response_path,
            patch_path=patch_path,
            generated_patch=patch_text,
            outcome=outcome,
            run_result=run_result,
            run_skipped=False,
            test_output_path=test_output_path,
        )

    def _build_report(
        self,
        baseline: _Baseline,
        without: VariantResult,
        with_: VariantResult,
        reference_patch: str,
    ) -> ComparisonReport:
        instance_id = self._test_spec.instance_id
        baseline_dict: Dict[str, Any] = {
            "run_result": baseline.run_result.to_dict(),
            "trace_path": str(
                Path(baseline.run_result.trace_path)
                if baseline.run_result.trace_path
                else self._baseline_output.trace_file(instance_id)
            ),
            "test_output_path": str(baseline.test_output_path),
            "trace_count": len(baseline.traces),
            "outcome": baseline.outcome.to_dict(),
        }
        comparison = {
            f"{Variant.WITHOUT_RUNTIME.value}_verdict": self._build_verdict(
                baseline.outcome, without
            ).value,
            f"{Variant.WITH_RUNTIME.value}_verdict": self._build_verdict(
                baseline.outcome, with_
            ).value,
        }
        return ComparisonReport(
            instance_id=instance_id,
            framework=baseline.run_result.framework,
            created_at=datetime.now(timezone.utc).isoformat(),
            baseline=baseline_dict,
            without_runtime=without,
            with_runtime=with_,
            patches={
                "reference_swebench": reference_patch,
                "llm_without_runtime": without.generated_patch,
                "llm_with_runtime": with_.generated_patch,
            },
            comparison=comparison,
        )

    @staticmethod
    def _read_text(path: Path) -> str:
        return (
            path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        )

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _read_json_list(path: Path) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    @staticmethod
    def _unique_in_order(items: Iterable[T]) -> List[T]:
        seen = set()
        ordered: List[T] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered

    def _collect_file_line_map(
        self, traces: List[Dict[str, Any]]
    ) -> Dict[str, List[int]]:
        file_lines: Dict[str, List[int]] = {}
        for trace in traces:
            frames = trace.get("frames", [])
            if isinstance(frames, list):
                for frame in frames:
                    if not isinstance(frame, dict):
                        continue
                    file_path = frame.get("file")
                    line = frame.get("line")
                    if not isinstance(file_path, str) or not isinstance(line, int):
                        continue
                    if not self._stdlib_filter.keep(
                        Frame(file=file_path, line=line, func=str(frame.get("func", "")))
                    ):
                        continue
                    file_lines.setdefault(file_path, []).append(line)

            exec_path = trace.get("exec_path", [])
            if isinstance(exec_path, list):
                for call in exec_path:
                    if not isinstance(call, dict):
                        continue
                    file_path = call.get("file")
                    line = call.get("line")
                    if not isinstance(file_path, str) or not isinstance(line, int):
                        continue
                    if not self._stdlib_filter.keep(
                        Frame(file=file_path, line=line, func=str(call.get("func", "")))
                    ):
                        continue
                    file_lines.setdefault(file_path, []).append(line)
        return file_lines

    @staticmethod
    def _select_context_files(
        file_line_map: Dict[str, List[int]], max_files: int
    ) -> List[str]:
        paths = list(file_line_map.keys())
        test_paths = [
            p for p in paths if "/tests/" in p or Path(p).name.startswith("test_")
        ]
        other_paths = [p for p in paths if p not in test_paths]
        ordered = test_paths + other_paths
        return ordered[:max_files]

    def _extract_setup_script(self, test_spec) -> str:
        setup_lines: List[str] = ["#!/bin/bash", "set -uxo pipefail"]
        for line in test_spec.eval_script_list:
            if "Start Test Output" in line:
                break
            setup_lines.append(line)
        return "\n".join(setup_lines) + "\n"

    def _read_files_from_image(
        self, image_name: str, file_paths: List[str]
    ) -> Dict[str, str]:
        source_map: Dict[str, str] = {}
        if not file_paths:
            return source_map

        container = None
        try:
            container = self._client.containers.create(
                image=image_name, command="sleep 300", tty=True
            )
            container.start()

            setup_script = self._extract_setup_script(self._test_spec)
            result = container.exec_run(
                cmd=["/bin/bash", "-c", setup_script],
                workdir=DOCKER_WORKDIR,
            )
            if result.exit_code != 0:
                self._logger.debug(
                    "Setup script returned %d; some files may be unavailable",
                    result.exit_code,
                )

            for file_path in file_paths:
                quoted = shlex.quote(file_path)
                cmd = ["/bin/sh", "-lc", f"cat {quoted}"]
                result = container.exec_run(cmd=cmd, workdir=DOCKER_WORKDIR)
                if result.exit_code == 0:
                    source_map[file_path] = result.output.decode(UTF8, errors="replace")
                else:
                    self._logger.debug(
                        "Could not read context file from image: %s", file_path
                    )
        except Exception as exc:
            self._logger.warning(
                "Failed extracting source snippets from image %s: %s", image_name, exc
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
        return source_map

    @staticmethod
    def _get_ctx_around_line_from_text(
        source: str, line_number: int, context_size: int
    ) -> str:
        if not source:
            return "<source unavailable>"
        lines = source.splitlines()
        if not lines:
            return "<source unavailable>"
        if line_number < 1:
            line_number = 1
        if line_number > len(lines):
            line_number = len(lines)
        start = max(1, line_number - context_size)
        end = min(len(lines), line_number + context_size)
        rendered = []
        for current in range(start, end + 1):
            marker = "->" if current == line_number else "  "
            rendered.append(f"{current} {marker} : {lines[current - 1]}")
        return "\n".join(rendered)

    def _serialize_frames_like_debugger(
        self,
        frames: List[Dict[str, Any]],
        source_map: Dict[str, str],
        context_size: int,
    ) -> str:
        blocks: List[str] = []
        for index, frame in enumerate(frames):
            if not isinstance(frame, dict):
                continue
            filename = str(frame.get("file", "<unknown>"))
            function_name = str(frame.get("func", "<unknown>"))
            line = frame.get("line", 1)
            line_number = line if isinstance(line, int) else 1
            source = source_map.get(filename, "")
            context = self._get_ctx_around_line_from_text(
                source, line_number, context_size
            )
            locals_payload = frame.get("locals", {})
            if isinstance(locals_payload, (dict, list)):
                locals_text = json.dumps(
                    locals_payload, ensure_ascii=False, indent=2, default=str
                )
            else:
                locals_text = str(locals_payload)
            block = textwrap.dedent(
                f"""\
                Block {index}:
                File: {filename}
                Function name: {function_name}
                Line: {line_number}
                Context:
                {context}
                Locals: {locals_text}
                """
            ).strip()
            blocks.append(block)

        if not blocks:
            return "<no runtime frames captured>"
        return "\n\n".join(blocks)

    @staticmethod
    def _summarize_failures(
        traces: List[Dict[str, Any]], test_output: str, max_items: int = 8
    ) -> str:
        if traces:
            lines = []
            for index, trace in enumerate(traces[:max_items], start=1):
                nodeid = trace.get("nodeid", "<unknown test>")
                exc_type = trace.get("exc_type", "<unknown exception>")
                message = trace.get("message", "")
                lines.append(f"{index}. {nodeid} -> {exc_type}: {message}")
            return "\n".join(lines)
        failure_lines = []
        for line in test_output.splitlines():
            if any(
                marker in line
                for marker in ("ERROR:", "FAIL:", "FAILED", "AssertionError", "Traceback")
            ):
                failure_lines.append(line)
        if not failure_lines:
            return "<no failure details available>"
        return "\n".join(failure_lines[:max_items])

    def _render_testcase_source(
        self,
        file_line_map: Dict[str, List[int]],
        selected_files: List[str],
        source_map: Dict[str, str],
        context_lines: int,
    ) -> str:
        test_candidates = [
            p
            for p in selected_files
            if "/tests/" in p or Path(p).name.startswith("test_")
        ]
        if not test_candidates:
            test_candidates = [
                p
                for p in file_line_map
                if "/tests/" in p or Path(p).name.startswith("test_")
            ]
        if not test_candidates:
            return "<testcase source not available from collected frames>"
        test_file = test_candidates[0]
        line_numbers = [
            line for line in file_line_map.get(test_file, []) if isinstance(line, int)
        ]
        focus_line = line_numbers[0] if line_numbers else 1
        source = source_map.get(test_file, "")
        snippet = self._get_ctx_around_line_from_text(source, focus_line, context_lines)
        return f"Test file: {test_file}\n{snippet}"

    def _render_related_source_context(
        self,
        selected_files: List[str],
        file_line_map: Dict[str, List[int]],
        source_map: Dict[str, str],
        context_lines: int,
        max_snippets_per_file: int = 2,
    ) -> str:
        blocks: List[str] = []
        for path in selected_files:
            line_numbers = self._unique_in_order(
                line
                for line in file_line_map.get(path, [])
                if isinstance(line, int)
            )
            source = source_map.get(path, "")
            if not source:
                blocks.append(f"File: {path}\n<source unavailable>")
                continue
            snippets = []
            for line_number in line_numbers[:max_snippets_per_file]:
                snippets.append(
                    self._get_ctx_around_line_from_text(source, line_number, context_lines)
                )
            if not snippets:
                snippets.append(self._get_ctx_around_line_from_text(source, 1, context_lines))
            blocks.append(f"File: {path}\n" + "\n---\n".join(snippets))
        return "\n\n".join(blocks) if blocks else "<no related source context available>"

    def _build_prompt(
        self,
        traces: List[Dict[str, Any]],
        failure_summary: str,
        testcase_source: str,
        related_context: str,
        include_runtime: bool,
        source_map: Dict[str, str],
    ) -> str:
        instance_id = self._test_spec.instance_id
        first_trace = traces[0] if traces else {}
        exception_type = str(first_trace.get("exc_type", "TestFailure"))
        exception_msg = str(first_trace.get("message", "See failure summary"))

        frames: List[Dict[str, Any]] = []
        exec_path_entries: List[Dict[str, Any]] = []
        for trace in traces:
            trace_frames = trace.get("frames", [])
            if isinstance(trace_frames, list):
                frames.extend([f for f in trace_frames if isinstance(f, dict)])
            trace_exec_path = trace.get("exec_path", [])
            if isinstance(trace_exec_path, list):
                exec_path_entries.extend(
                    [e for e in trace_exec_path if isinstance(e, dict)]
                )

        frame_context_lines = self._config.context_lines
        if include_runtime:
            runtime_trace = self._serialize_frames_like_debugger(
                frames, source_map, frame_context_lines
            )
            if exec_path_entries:
                ep_lines = []
                seen = set()
                for entry in exec_path_entries:
                    f = entry.get("file", "?")
                    func = entry.get("func", "?")
                    line = entry.get("line", "?")
                    if not isinstance(f, str):
                        continue
                    line_int = line if isinstance(line, int) else 0
                    if not self._stdlib_filter.keep(
                        Frame(file=f, line=line_int, func=str(func))
                    ):
                        continue
                    key = (f, func)
                    if key in seen:
                        continue
                    seen.add(key)
                    ep_lines.append(f"  {f}:{line} in {func}()")
                runtime_trace += (
                    "\n\n## Execution path (functions called during test)\n"
                    + "\n".join(ep_lines)
                )
        else:
            runtime_trace = "Runtime trace intentionally omitted for this run."

        prompt_prefix_body = (
            f"Repository instance: {instance_id}\n\n"
            f"## Failure summary\n{failure_summary}\n\n"
            f"## Testcase source code\n{testcase_source}\n\n"
            f"## Related source context (small)\n{related_context}"
        )
        exception_body = f"Type: {exception_type}\nMessage: {exception_msg}"

        return (
            PromptBuilder()
            .add_section("context", prompt_prefix_body)
            .add_section("intro", load_prompt("debugger/intro.txt").rstrip("\n"))
            .add_section("exception", exception_body)
            .add_section("runtime_trace", runtime_trace)
            .add_section("instructions", load_prompt("debugger/instructions.txt").rstrip("\n"))
            .add_section(
                "strict_patch_requirements",
                load_prompt("swebench/strict_patch_requirements.txt").rstrip("\n"),
            )
            .build()
        )

    @staticmethod
    def _find_diff_start(text: str) -> Optional[int]:
        indexes: List[int] = []
        for pattern in (r"^diff --git ", r"^--- "):
            match = re.search(pattern, text, flags=re.MULTILINE)
            if match:
                indexes.append(match.start())
        return min(indexes) if indexes else None

    def _extract_unified_diff(self, response_text: str) -> str:
        if not response_text:
            return ""
        candidates = []
        fenced_blocks = re.findall(
            r"```(?:diff)?\s*\n(.*?)```", response_text, flags=re.DOTALL
        )
        candidates.extend(fenced_blocks)
        candidates.append(response_text)
        for candidate in candidates:
            start_index = self._find_diff_start(candidate)
            if start_index is None:
                continue
            patch = candidate[start_index:].strip()
            if patch:
                return patch + ("\n" if not patch.endswith("\n") else "")
        return ""

    @staticmethod
    def _parse_test_output(text: str) -> Outcome:
        status = Status.UNKNOWN
        if re.search(r"^FAILED\b", text, flags=re.MULTILINE) or re.search(
            r"\b\d+\s+failed\b", text
        ):
            status = Status.FAILED
        elif re.search(r"^OK\b", text, flags=re.MULTILINE) or re.search(
            r"\b0\s+failed\b", text
        ):
            status = Status.PASSED

        failure_count: Optional[int] = None
        for match in re.finditer(r"(?:failures|errors)=(\d+)", text):
            if failure_count is None:
                failure_count = 0
            failure_count += int(match.group(1))
        failed_match = re.search(r"(\d+)\s+failed\b", text)
        if failed_match:
            failed_count = int(failed_match.group(1))
            failure_count = (
                failed_count
                if failure_count is None
                else max(failure_count, failed_count)
            )
        if status is Status.PASSED:
            failure_count = 0

        ran_match = re.search(r"Ran\s+(\d+)\s+tests", text)
        ran_tests = int(ran_match.group(1)) if ran_match else None

        summary_line = ""
        for pattern in (r"^FAILED.*$", r"^OK.*$", r"^=+.*(?:failed|passed).*$"):
            summary_match = re.search(pattern, text, flags=re.MULTILINE)
            if summary_match:
                summary_line = summary_match.group(0).strip()
                break

        return Outcome(
            status=status,
            failure_count=failure_count,
            ran_tests=ran_tests,
            summary_line=summary_line,
        )

    def _resolve_test_output_path(
        self,
        run_result: RunResult,
        output_manager: TraceOutputManager,
        instance_id: str,
    ) -> Path:
        if run_result.trace_path:
            trace_file = Path(run_result.trace_path)
            if trace_file.exists():
                return trace_file.parent / "test_output.txt"
        return output_manager.test_output_file(instance_id)

    @staticmethod
    def _build_verdict(baseline: Outcome, variant: VariantResult) -> Verdict:
        if variant.run_skipped:
            return Verdict.NOT_RUN
        v_outcome = variant.outcome
        baseline_status = baseline.status
        variant_status = v_outcome.status
        if variant_status in {Status.APPLY_FAILED, Status.NOT_RUN}:
            return Verdict.NOT_RUN
        baseline_failures = baseline.failure_count
        variant_failures = v_outcome.failure_count
        if baseline_status is not Status.PASSED and variant_status is Status.PASSED:
            return Verdict.FIXED
        if isinstance(baseline_failures, int) and isinstance(variant_failures, int):
            if variant_failures < baseline_failures:
                return Verdict.IMPROVED
            if variant_failures == baseline_failures:
                return Verdict.UNCHANGED
            if variant_failures > baseline_failures:
                return Verdict.REGRESSED
        return Verdict.UNKNOWN
