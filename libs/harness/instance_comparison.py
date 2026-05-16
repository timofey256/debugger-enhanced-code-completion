from __future__ import annotations

import json
import logging
import re
import shlex
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, NamedTuple, Optional, Tuple, TypeVar

import docker

from libs.frames import (
    ExecutionPathSerializer,
    Frame,
    FrameSerializer,
    select_most_informative_trace,
)
from libs.harness.framework_detector import FrameworkDetector
from libs.harness.io_utils import read_text, render_source_context, write_text
from libs.harness.localization_metrics import compute_localization_accuracy
from libs.harness.trace_output import TraceOutputManager
from libs.harness.traced_runner import RunResult, TracedInstanceRunner
from libs.llm.connector import ToolSessionResult
from libs.llm.tooling import (
    ProjectPathResolver,
    ProjectToolContext,
    RuntimeToolContext,
    ToolCatalog,
    ToolSessionContext,
    create_with_runtime_catalog,
    create_without_runtime_catalog,
)

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
    success: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "failure_count": self.failure_count,
            "ran_tests": self.ran_tests,
            "summary_line": self.summary_line,
            "success": self.success,
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
    token_usage: Dict[str, int] = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    localization_accuracy: Dict[str, bool] = field(default_factory=lambda: {"correct_file": False, "correct_function": False, "correct_line": False})

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
            "token_usage": self.token_usage,
            "localization_accuracy": self.localization_accuracy,
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
    enable_tools: bool = True
    max_tool_turns: int = 8
    max_tool_output_chars: int = 20000


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
    trace: Mapping[str, Any]
    test_output_path: Path
    test_output: str
    outcome: Outcome
    file_line_map: Dict[str, List[int]]
    selected_files: List[str]
    source_map: Dict[str, str]


def _trace_frames(trace: Mapping[str, Any]) -> Tuple[Frame, ...]:
    return tuple(
        f for f in (Frame.from_raw(d) for d in trace.get("frames", [])) if f is not None
    )


def _trace_exec_path(trace: Mapping[str, Any]) -> Tuple[Frame, ...]:
    return tuple(
        f for f in (Frame.from_raw(d) for d in trace.get("exec_path", [])) if f is not None
    )


def _trace_step_frames(trace: Mapping[str, Any]) -> Tuple[Frame, ...]:
    return tuple(
        f for f in (Frame.from_raw(d) for d in trace.get("step_frames", [])) if f is not None
    )


class _Prompts(NamedTuple):
    without: str
    with_: str
    failure_summary: str
    testcase_source: str


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

    def run(self) -> Optional[ComparisonReport]:
        instance_id = self._test_spec.instance_id
        self._logger.info("%s", "=" * 70)
        self._logger.info("Processing debugger comparison for %s", instance_id)
        self._logger.info("%s", "=" * 70)
        try:
            return self._run_unsafe()
        except Exception as exc:
            self._logger.exception(
                "Comparison failed for %s: %s", instance_id, exc
            )
            error_path = self._artifacts_dir / "comparison_error.json"
            write_text(
                error_path,
                json.dumps(
                    {
                        "instance_id": instance_id,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
            )
            return None

    def _run_unsafe(self) -> ComparisonReport:
        instance_id = self._test_spec.instance_id
        reference_patch = str(self._reference_pred.get(KEY_PREDICTION, ""))
        write_text(self._artifacts_dir / "reference_patch.diff", reference_patch)

        with self._baseline_output.project_scope(instance_id) as project:
            baseline = self._collect_baseline()
            prompts = self._build_prompts(baseline)

            without = self._run_variant(
                Variant.WITHOUT_RUNTIME,
                prompts.without,
                self._without_runner,
                self._without_output,
                baseline=baseline,
                project_root=project.path,
            )
            with_ = self._run_variant(
                Variant.WITH_RUNTIME,
                prompts.with_,
                self._with_runner,
                self._with_output,
                baseline=baseline,
                project_root=project.path,
            )

        report = self._build_report(baseline, without, with_, reference_patch)

        report_path = self._artifacts_dir / "comparison_report.json"
        write_text(
            report_path, json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
        )
        self._logger.info("Saved report: %s", report_path)
        return report

    def _collect_baseline(self) -> _Baseline:
        instance_id = self._test_spec.instance_id
        run_result = self._baseline_runner.run(self._reference_pred, skip_patch=True)

        trace = select_most_informative_trace(list(run_result.traces))

        test_output_path = self._resolve_test_output_path(run_result, self._baseline_output, instance_id)
        test_output = read_text(test_output_path)
        outcome = self._parse_test_output(test_output)

        all_frames = _trace_frames(trace) + _trace_exec_path(trace)
        file_line_map = self._collect_file_line_map(all_frames)
        selected_files = self._select_context_files(file_line_map, self._config.max_context_files)

        all_trace_files = list(file_line_map.keys())
        files_to_read = list(dict.fromkeys(selected_files + all_trace_files))
        source_map = self._read_files_from_image(self._test_spec.instance_image_key, files_to_read)

        return _Baseline(
            run_result=run_result,
            trace=trace,
            test_output_path=test_output_path,
            test_output=test_output,
            outcome=outcome,
            file_line_map=file_line_map,
            selected_files=selected_files,
            source_map=source_map,
        )

    def _build_prompts(self, baseline: _Baseline) -> _Prompts:
        failure_summary = self._summarize_failures(baseline.trace, baseline.test_output)
        testcase_source = self._render_testcase_source(
            baseline.file_line_map,
            baseline.selected_files,
            baseline.source_map,
            self._config.test_context_lines,
        )

        without = self._build_prompt(
            trace=baseline.trace,
            failure_summary=failure_summary,
            testcase_source=testcase_source,
            include_runtime=False,
            source_map=baseline.source_map,
        )
        with_ = self._build_prompt(
            trace=baseline.trace,
            failure_summary=failure_summary,
            testcase_source=testcase_source,
            include_runtime=True,
            source_map=baseline.source_map,
        )
        return _Prompts(
            without=without,
            with_=with_,
            failure_summary=failure_summary,
            testcase_source=testcase_source,
        )

    def _run_variant(
        self,
        variant: Variant,
        prompt: str,
        runner: TracedInstanceRunner,
        output_manager: TraceOutputManager,
        *,
        baseline: Optional[_Baseline] = None,
        project_root: Optional[Path] = None,
    ) -> VariantResult:
        variant_name = variant.value
        prompt_path = self._artifacts_dir / f"prompt_{variant_name}.txt"
        response_path = self._artifacts_dir / f"response_{variant_name}.txt"
        patch_path = self._artifacts_dir / f"patch_{variant_name}.diff"

        write_text(prompt_path, prompt)

        if self._config.enable_tools and baseline is not None:
            session = self._run_tool_session(variant, prompt, baseline, project_root=project_root)
            patch_text = session.patch
            response_text = session.render()
            token_usage = {"input_tokens": session.input_tokens, "output_tokens": session.output_tokens}
        else:
            result = self._llm.complete_code(prompt, max_tokens=self._config.max_tokens)
            response_text = result.patch
            patch_text = self._extract_unified_diff(response_text)
            token_usage = {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens}
        write_text(response_path, response_text)
        write_text(patch_path, patch_text)

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
                token_usage=token_usage,
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
                token_usage=token_usage,
            )

        test_output_path = self._resolve_test_output_path(
            run_result, output_manager, instance_id
        )
        test_output_text = read_text(test_output_path)
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
            token_usage=token_usage,
        )

    def _build_report(
        self,
        baseline: _Baseline,
        without: VariantResult,
        with_: VariantResult,
        reference_patch: str,
    ) -> ComparisonReport:
        instance_id = self._test_spec.instance_id
        without.localization_accuracy = compute_localization_accuracy(without.generated_patch, reference_patch)
        with_.localization_accuracy = compute_localization_accuracy(with_.generated_patch, reference_patch)
        baseline_dict: Dict[str, Any] = {
            "run_result": baseline.run_result.to_dict(),
            "trace_path": str(
                Path(baseline.run_result.trace_path)
                if baseline.run_result.trace_path
                else self._baseline_output.trace_file(instance_id)
            ),
            "test_output_path": str(baseline.test_output_path),
            "trace_count": 1 if baseline.trace else 0,
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
    def _collect_file_line_map(
        frames: Iterable[Frame],
    ) -> Dict[str, List[int]]:
        file_lines: Dict[str, List[int]] = {}
        for frame in frames:
            file_lines.setdefault(frame.file, []).append(frame.line)
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

    def _build_tool_session_context(
        self, baseline: _Baseline, include_runtime: bool, project_root: Path
    ) -> ToolSessionContext:
        if not project_root.exists() or not any(project_root.iterdir()):
            raise RuntimeError(
                f"Project mirror at {project_root} is empty; "
                "baseline run did not populate /project_mirror."
            )
        resolver = ProjectPathResolver(
            project_root, container_project_root=DOCKER_WORKDIR
        )
        project_ctx = ProjectToolContext(
            resolver=resolver,
            source_map=baseline.source_map,
            context_size=self._config.context_lines,
        )
        runtime_ctx: Optional[RuntimeToolContext] = None
        if include_runtime:
            runtime_ctx = RuntimeToolContext(
                frames=_trace_frames(baseline.trace),
                execution_path=_trace_exec_path(baseline.trace),
                step_frames=_trace_step_frames(baseline.trace),
                trace=dict(baseline.trace) if baseline.trace else {},
                test_output_path=baseline.test_output_path,
            )
        return ToolSessionContext(project=project_ctx, runtime=runtime_ctx)

    def _run_tool_session(
        self,
        variant: Variant,
        prompt: str,
        baseline: _Baseline,
        *,
        project_root: Optional[Path] = None,
    ) -> ToolSessionResult:
        include_runtime = variant is Variant.WITH_RUNTIME
        if project_root is None:
            project_root = self._baseline_output.project_dir(
                self._test_spec.instance_id
            )
        context = self._build_tool_session_context(
            baseline, include_runtime=include_runtime, project_root=project_root
        )
        catalog: ToolCatalog = (
            create_with_runtime_catalog()
            if include_runtime
            else create_without_runtime_catalog()
        )
        return self._llm.complete_with_tools(
            prompt,
            catalog=catalog,
            context=context,
            max_tool_turns=self._config.max_tool_turns,
            max_tokens=self._config.max_tokens,
            max_tool_output_chars=self._config.max_tool_output_chars,
        )

    @staticmethod
    def _summarize_failures(
        trace: Mapping[str, Any], test_output: str, max_items: int = 8
    ) -> str:
        if trace:
            nodeid = trace.get("nodeid", "<unknown test>")
            exc_type = trace.get("exc_type", "<unknown exception>")
            message = trace.get("message", "")
            return f"1. {nodeid} -> {exc_type}: {message}"
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
        snippet = render_source_context(source, focus_line, context_lines)
        return f"Test file: {test_file}\n{snippet}"

    def _build_prompt(
        self,
        trace: Mapping[str, Any],
        failure_summary: str,
        testcase_source: str,
        include_runtime: bool,
        source_map: Dict[str, str],
    ) -> str:
        exception_type = str(trace.get("exc_type", "TestFailure"))
        exception_msg = str(trace.get("message", "See failure summary"))

        frames = _trace_frames(trace)
        exec_path_frames = _trace_exec_path(trace)

        if include_runtime:
            execution_path = ExecutionPathSerializer().to_string(exec_path_frames)
            runtime_frames = FrameSerializer(
                source_map, self._config.context_lines
            ).to_string_many(frames)
            runtime_specific = load_prompt("debugger/runtime_specific.txt").rstrip("\n")
        else:
            execution_path = "intentionally omitted"
            runtime_frames = "intentionally omitted"
            runtime_specific = "intentionally omitted"

        return (
            PromptBuilder()
            .add_section("intro", load_prompt("debugger/intro.txt").rstrip("\n"))
            .add_section("instructions", load_prompt("debugger/instructions.txt").rstrip("\n"))
            .add_section("runtime_specific", runtime_specific)
            .add_section("failure_summary", failure_summary)
            .add_section("testcase_source", testcase_source)
            .add_section("exception_type", exception_type)
            .add_section("exception_body", exception_msg)
            .add_section("execution_path", execution_path)
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
            success="PASSED" in text,
        )

    def _resolve_test_output_path(self, run_result: RunResult, output_manager: TraceOutputManager, instance_id: str) -> Path:
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
