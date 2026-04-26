#!/usr/bin/env python3
"""
Run SWE-bench patch-generation comparison with and without runtime traces.

Per instance:
1) Run baseline without applying patch (collect failures + traces)
2) Generate LLM patch from prompt WITHOUT runtime trace section, re-run, evaluate
3) Generate LLM patch from prompt WITH runtime trace section, re-run, evaluate
4) Persist report artifacts with reference and generated patches
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shlex
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import docker

REPO_ROOT = Path(__file__).resolve().parents[3]

from libs.env import require_env

sys.path.insert(0, require_env("SWE_BENCH_PATH"))

from apps.backend.server_pkg.generate_prompt import _TEMPLATE as DEBUGGER_TEMPLATE
from llm.connector import LLMConnector

from swebench.harness.constants import (
    DOCKER_WORKDIR,
    KEY_INSTANCE_ID,
    KEY_MODEL,
    KEY_PREDICTION,
    UTF8,
)
from swebench.harness.docker_build import build_env_images
from swebench.harness.test_spec.test_spec import make_test_spec
from swebench.harness.utils import get_predictions_from_file, load_swebench_dataset

from research.swebench.harness.wrapper import run_instance_with_traces

STRICT_PATCH_REQUIREMENTS = textwrap.dedent(
    """\
    STRICT PATCH FORMAT REQUIREMENTS (highest priority):
    - Output only patch text; no prose and no markdown fences.
    - Use git-compatible unified diff format with file headers:
      - `diff --git a/<path> b/<path>`
      - `--- a/<path>`
      - `+++ b/<path>`
    - Paths must be repository-relative (e.g. `django/utils/autoreload.py`).
    - Never use absolute paths such as `/testbed/...`.
    """
).strip()


def setup_logging(verbose: bool = False) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


def unique_in_order(items: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _is_project_file(file_path: str) -> bool:
    """Check if a file is project source code (not stdlib/site-packages)."""
    if not file_path.endswith(".py"):
        return False
    if "site-packages" in file_path:
        return False
    # Reject conda/system stdlib (e.g. /opt/miniconda3/envs/testbed/lib/python3.9/...)
    if "/lib/python" in file_path:
        return False
    # Reject our injected tracer conftest
    if file_path.endswith("/conftest.py"):
        return False
    return True


def collect_file_line_map(traces: List[Dict[str, Any]]) -> Dict[str, List[int]]:
    file_lines: Dict[str, List[int]] = {}
    for trace in traces:
        frames = trace.get("frames", [])
        if not isinstance(frames, list):
            continue
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            file_path = frame.get("file")
            line = frame.get("line")
            if not isinstance(file_path, str) or not _is_project_file(file_path):
                continue
            if not isinstance(line, int):
                continue
            file_lines.setdefault(file_path, []).append(line)
        # Also include files from execution path (functions called during test
        # that returned successfully and thus don't appear in exception traceback)
        exec_path = trace.get("exec_path", [])
        if isinstance(exec_path, list):
            for call in exec_path:
                if not isinstance(call, dict):
                    continue
                file_path = call.get("file")
                line = call.get("line")
                if not isinstance(file_path, str) or not _is_project_file(file_path):
                    continue
                if not isinstance(line, int):
                    continue
                file_lines.setdefault(file_path, []).append(line)
    return file_lines


def select_context_files(file_line_map: Dict[str, List[int]], max_files: int) -> List[str]:
    paths = list(file_line_map.keys())
    test_paths = [
        p for p in paths if "/tests/" in p or Path(p).name.startswith("test_")
    ]
    other_paths = [p for p in paths if p not in test_paths]
    ordered = test_paths + other_paths
    return ordered[:max_files]


def _extract_setup_script(test_spec) -> str:
    """Extract eval script commands up to (but not including) the test execution.

    The eval script contains repo setup (git checkout, git apply for test files,
    pip install, etc.) followed by the actual test command bracketed by
    ``>>>>> Start Test Output``.  We replay the setup portion so that test files
    created by ``git apply`` are available for reading.
    """
    setup_lines: List[str] = ["#!/bin/bash", "set -uxo pipefail"]
    for line in test_spec.eval_script_list:
        if "Start Test Output" in line:
            break
        setup_lines.append(line)
    return "\n".join(setup_lines) + "\n"


def read_files_from_image(
    client: docker.DockerClient,
    image_name: str,
    file_paths: List[str],
    logger: logging.Logger,
    test_spec=None,
) -> Dict[str, str]:
    source_map: Dict[str, str] = {}
    if not file_paths:
        return source_map

    container = None
    try:
        container = client.containers.create(image=image_name, command="sleep 300", tty=True)
        container.start()

        # Replay eval-script setup so test files (created by git apply) exist
        if test_spec is not None:
            setup_script = _extract_setup_script(test_spec)
            result = container.exec_run(
                cmd=["/bin/bash", "-c", setup_script],
                workdir=DOCKER_WORKDIR,
            )
            if result.exit_code != 0:
                logger.debug(
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
                logger.debug("Could not read context file from image: %s", file_path)
    except Exception as exc:
        logger.warning("Failed extracting source snippets from image %s: %s", image_name, exc)
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass

    return source_map


def get_ctx_around_line_from_text(source: str, line_number: int, context_size: int) -> str:
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


def serialize_frames_like_debugger(
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
        context = get_ctx_around_line_from_text(source, line_number, context_size)

        locals_payload = frame.get("locals", {})
        if isinstance(locals_payload, (dict, list)):
            locals_text = json.dumps(
                locals_payload,
                ensure_ascii=False,
                indent=2,
                default=str,
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


def summarize_failures(traces: List[Dict[str, Any]], test_output: str, max_items: int = 8) -> str:
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
        if any(marker in line for marker in ("ERROR:", "FAIL:", "FAILED", "AssertionError", "Traceback")):
            failure_lines.append(line)
    if not failure_lines:
        return "<no failure details available>"
    return "\n".join(failure_lines[:max_items])


def render_testcase_source(
    file_line_map: Dict[str, List[int]],
    selected_files: List[str],
    source_map: Dict[str, str],
    context_lines: int,
) -> str:
    test_candidates = [
        path
        for path in selected_files
        if "/tests/" in path or Path(path).name.startswith("test_")
    ]
    if not test_candidates:
        test_candidates = [
            path
            for path in file_line_map
            if "/tests/" in path or Path(path).name.startswith("test_")
        ]

    if not test_candidates:
        return "<testcase source not available from collected frames>"

    test_file = test_candidates[0]
    line_numbers = [line for line in file_line_map.get(test_file, []) if isinstance(line, int)]
    focus_line = line_numbers[0] if line_numbers else 1
    source = source_map.get(test_file, "")
    snippet = get_ctx_around_line_from_text(source, focus_line, context_lines)
    return f"Test file: {test_file}\n{snippet}"


def render_related_source_context(
    selected_files: List[str],
    file_line_map: Dict[str, List[int]],
    source_map: Dict[str, str],
    context_lines: int,
    max_snippets_per_file: int = 2,
) -> str:
    blocks: List[str] = []

    for path in selected_files:
        line_numbers = unique_in_order(
            [str(line) for line in file_line_map.get(path, []) if isinstance(line, int)]
        )
        source = source_map.get(path, "")

        if not source:
            blocks.append(f"File: {path}\n<source unavailable>")
            continue

        snippets = []
        for line_text in line_numbers[:max_snippets_per_file]:
            line_number = int(line_text)
            snippets.append(get_ctx_around_line_from_text(source, line_number, context_lines))

        if not snippets:
            snippets.append(get_ctx_around_line_from_text(source, 1, context_lines))

        blocks.append(f"File: {path}\n" + "\n---\n".join(snippets))

    return "\n\n".join(blocks) if blocks else "<no related source context available>"


def build_prompt(
    instance_id: str,
    traces: List[Dict[str, Any]],
    failure_summary: str,
    testcase_source: str,
    related_context: str,
    include_runtime: bool,
    source_map: Dict[str, str],
    frame_context_lines: int,
) -> str:
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
            exec_path_entries.extend([e for e in trace_exec_path if isinstance(e, dict)])

    if include_runtime:
        runtime_trace = serialize_frames_like_debugger(frames, source_map, frame_context_lines)
        # Append execution path summary (functions called during test, even if
        # they returned successfully and don't appear in exception traceback)
        if exec_path_entries:
            ep_lines = []
            seen = set()
            for entry in exec_path_entries:
                f = entry.get("file", "?")
                func = entry.get("func", "?")
                line = entry.get("line", "?")
                # Only show project files (skip stdlib/site-packages that may leak through)
                if "site-packages" in f or not ("/testbed/" in f or f.endswith(".py")):
                    continue
                key = (f, func)
                if key in seen:
                    continue
                seen.add(key)
                ep_lines.append(f"  {f}:{line} in {func}()")
                runtime_trace += "\n\n## Execution path (functions called during test)\n" + "\n".join(ep_lines)
    else:
        runtime_trace = "Runtime trace intentionally omitted for this run."

    prompt_prefix = textwrap.dedent(
        f"""\
        Repository instance: {instance_id}

        ## Failure summary
        {failure_summary}

        ## Testcase source code
        {testcase_source}

        ## Related source context (small)
        {related_context}
        """
    ).strip()

    debugger_instructions = DEBUGGER_TEMPLATE.format(
        exception_type=exception_type,
        exception_msg=exception_msg,
        runtime_trace=runtime_trace,
    )

    return f"{prompt_prefix}\n\n{debugger_instructions}\n\n{STRICT_PATCH_REQUIREMENTS}"


def _find_diff_start(text: str) -> Optional[int]:
    indexes: List[int] = []
    for pattern in (r"^diff --git ", r"^--- "):
        match = re.search(pattern, text, flags=re.MULTILINE)
        if match:
            indexes.append(match.start())
    return min(indexes) if indexes else None


def extract_unified_diff(response_text: str) -> str:
    if not response_text:
        return ""

    candidates = []
    fenced_blocks = re.findall(r"```(?:diff)?\s*\n(.*?)```", response_text, flags=re.DOTALL)
    candidates.extend(fenced_blocks)
    candidates.append(response_text)

    for candidate in candidates:
        start_index = _find_diff_start(candidate)
        if start_index is None:
            continue
        patch = candidate[start_index:].strip()
        if patch:
            return patch + ("\n" if not patch.endswith("\n") else "")

    return ""


def parse_test_output(text: str) -> Dict[str, Any]:
    status = "unknown"

    if re.search(r"^FAILED\b", text, flags=re.MULTILINE) or re.search(r"\b\d+\s+failed\b", text):
        status = "failed"
    elif re.search(r"^OK\b", text, flags=re.MULTILINE) or re.search(r"\b0\s+failed\b", text):
        status = "passed"

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

    if status == "passed":
        failure_count = 0

    ran_match = re.search(r"Ran\s+(\d+)\s+tests", text)
    ran_tests = int(ran_match.group(1)) if ran_match else None

    summary_line = ""
    for pattern in (r"^FAILED.*$", r"^OK.*$", r"^=+.*(?:failed|passed).*$"):
        summary_match = re.search(pattern, text, flags=re.MULTILINE)
        if summary_match:
            summary_line = summary_match.group(0).strip()
            break

    return {
        "status": status,
        "failure_count": failure_count,
        "ran_tests": ran_tests,
        "summary_line": summary_line,
    }


def resolve_test_output_path(result: Dict[str, Any], run_base: Path, instance_id: str) -> Path:
    trace_path = result.get("trace_path")
    if isinstance(trace_path, str) and trace_path:
        trace_file = Path(trace_path)
        if trace_file.exists():
            return trace_file.parent / "test_output.txt"
    return run_base / instance_id / "test_output.txt"


def build_verdict(baseline: Dict[str, Any], variant_result: Dict[str, Any]) -> str:
    if variant_result.get("run_skipped"):
        return "not_run"

    variant = variant_result.get("outcome", {})
    if not isinstance(variant, dict):
        variant = {}

    baseline_status = baseline.get("status", "unknown")
    variant_status = variant.get("status", "unknown")
    if variant_status in {"apply_failed", "not_run"}:
        return "not_run"

    baseline_failures = baseline.get("failure_count")
    variant_failures = variant.get("failure_count")

    if baseline_status != "passed" and variant_status == "passed":
        return "fixed"

    if isinstance(baseline_failures, int) and isinstance(variant_failures, int):
        if variant_failures < baseline_failures:
            return "improved"
        if variant_failures == baseline_failures:
            return "unchanged"
        if variant_failures > baseline_failures:
            return "regressed"

    return "unknown"


def run_patch_variant(
    variant_name: str,
    prompt: str,
    llm: LLMConnector,
    max_tokens: int,
    reference_pred: Dict[str, Any],
    model_name: str,
    test_spec,
    client: docker.DockerClient,
    run_id: str,
    run_base: Path,
    trace_collector_dir: Path,
    timeout: Optional[int],
    force_rebuild: bool,
    nocache: bool,
    logger: logging.Logger,
    artifacts_dir: Path,
) -> Dict[str, Any]:
    prompt_path = artifacts_dir / f"prompt_{variant_name}.txt"
    response_path = artifacts_dir / f"response_{variant_name}.txt"
    patch_path = artifacts_dir / f"patch_{variant_name}.diff"

    write_text(prompt_path, prompt)

    response_text = llm.complete_code(prompt, max_tokens=max_tokens)
    write_text(response_path, response_text)

    patch_text = extract_unified_diff(response_text)
    write_text(patch_path, patch_text)

    result: Dict[str, Any] = {
        "variant": variant_name,
        "prompt_path": str(prompt_path),
        "response_path": str(response_path),
        "patch_path": str(patch_path),
        "generated_patch": patch_text,
    }

    if not patch_text.strip():
        result["run_skipped"] = True
        result["run_result"] = {
            "success": False,
            "error": "No unified diff could be extracted from model response.",
        }
        result["outcome"] = {
            "status": "not_run",
            "failure_count": None,
            "ran_tests": None,
            "summary_line": "not run (no patch extracted)",
        }
        return result

    variant_pred = dict(reference_pred)
    variant_pred[KEY_PREDICTION] = patch_text
    variant_pred[KEY_MODEL] = f"{model_name}-{variant_name}"

    run_result = run_instance_with_traces(
        test_spec=test_spec,
        pred=variant_pred,
        client=client,
        run_id=f"{run_id}_{variant_name}",
        trace_output_base=str(run_base),
        trace_collector_dir=str(trace_collector_dir),
        timeout=timeout,
        force_rebuild=force_rebuild,
        nocache=nocache,
        skip_patch=False,
        logger=logger,
    )

    if not run_result.get("success"):
        run_error = str(run_result.get("error", "variant execution failed"))
        status = "apply_failed" if "Patch Apply Failed" in run_error else "not_run"

        result["run_skipped"] = True
        result["run_result"] = run_result
        result["test_output_path"] = str(resolve_test_output_path(run_result, run_base, test_spec.instance_id))
        result["outcome"] = {
            "status": status,
            "failure_count": None,
            "ran_tests": None,
            "summary_line": run_error,
        }
        return result

    test_output_path = resolve_test_output_path(run_result, run_base, test_spec.instance_id)
    test_output_text = read_text(test_output_path)
    outcome = parse_test_output(test_output_text)

    result["run_skipped"] = False
    result["run_result"] = run_result
    result["test_output_path"] = str(test_output_path)
    result["outcome"] = outcome
    return result


def build_markdown_report(report: Dict[str, Any]) -> str:
    baseline = report["baseline"]
    no_runtime = report["without_runtime"]
    with_runtime = report["with_runtime"]

    return textwrap.dedent(
        f"""\
        # Debugger Patch Comparison — {report['instance_id']}

        ## Baseline
        - Framework: {report.get('framework', 'unknown')}
        - Status: {baseline['outcome'].get('status')}
        - Failure count: {baseline['outcome'].get('failure_count')}
        - Summary: {baseline['outcome'].get('summary_line')}

        ## Without Runtime Information
        - Status: {no_runtime['outcome'].get('status')}
        - Failure count: {no_runtime['outcome'].get('failure_count')}
        - Summary: {no_runtime['outcome'].get('summary_line')}
        - Verdict vs baseline: {report['comparison'].get('without_runtime_verdict')}

        ## With Runtime Information
        - Status: {with_runtime['outcome'].get('status')}
        - Failure count: {with_runtime['outcome'].get('failure_count')}
        - Summary: {with_runtime['outcome'].get('summary_line')}
        - Verdict vs baseline: {report['comparison'].get('with_runtime_verdict')}

        ## Reference SWE-bench Patch
        ```diff
        {report['patches']['reference_swebench']}
        ```

        ## LLM Patch (Without Runtime)
        ```diff
        {report['patches']['llm_without_runtime']}
        ```

        ## LLM Patch (With Runtime)
        ```diff
        {report['patches']['llm_with_runtime']}
        ```
        """
    )


def process_instance(
    args,
    client: docker.DockerClient,
    test_spec,
    reference_pred: Dict[str, Any],
    trace_collector_dir: Path,
    logger: logging.Logger,
    output_dir: Path,
) -> Dict[str, Any]:
    instance_id = test_spec.instance_id
    logger.info("\n%s", "=" * 70)
    logger.info("Processing debugger comparison for %s", instance_id)
    logger.info("%s", "=" * 70)

    baseline_base = output_dir / "baseline"
    no_runtime_base = output_dir / "without_runtime"
    with_runtime_base = output_dir / "with_runtime"
    artifacts_dir = output_dir / "artifacts" / instance_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    reference_patch = str(reference_pred.get(KEY_PREDICTION, ""))
    write_text(artifacts_dir / "reference_patch.diff", reference_patch)

    baseline_result = run_instance_with_traces(
        test_spec=test_spec,
        pred=reference_pred,
        client=client,
        run_id=f"{args.run_id}_baseline",
        trace_output_base=str(baseline_base),
        trace_collector_dir=str(trace_collector_dir),
        timeout=args.timeout,
        force_rebuild=args.force_rebuild,
        nocache=args.nocache,
        skip_patch=True,
        logger=logger,
    )

    baseline_trace_path = Path(baseline_result.get("trace_path", "")) if baseline_result.get("trace_path") else baseline_base / instance_id / "auto_debug.json"
    baseline_traces = read_json_list(baseline_trace_path)

    baseline_test_output_path = resolve_test_output_path(baseline_result, baseline_base, instance_id)
    baseline_test_output = read_text(baseline_test_output_path)
    baseline_outcome = parse_test_output(baseline_test_output)

    file_line_map = collect_file_line_map(baseline_traces)
    selected_files = select_context_files(file_line_map, args.max_context_files)
    # Read source for all files referenced in traces (not just selected context files)
    # so that runtime trace blocks can show source context
    all_trace_files = list(file_line_map.keys())
    files_to_read = list(dict.fromkeys(selected_files + all_trace_files))
    source_map = read_files_from_image(
        client=client,
        image_name=test_spec.instance_image_key,
        file_paths=files_to_read,
        logger=logger,
        test_spec=test_spec,
    )

    failure_summary = summarize_failures(baseline_traces, baseline_test_output)
    testcase_source = render_testcase_source(
        file_line_map=file_line_map,
        selected_files=selected_files,
        source_map=source_map,
        context_lines=args.test_context_lines,
    )
    related_context = render_related_source_context(
        selected_files=selected_files,
        file_line_map=file_line_map,
        source_map=source_map,
        context_lines=args.context_lines,
    )

    no_runtime_prompt = build_prompt(
        instance_id=instance_id,
        traces=baseline_traces,
        failure_summary=failure_summary,
        testcase_source=testcase_source,
        related_context=related_context,
        include_runtime=False,
        source_map=source_map,
        frame_context_lines=args.context_lines,
    )

    with_runtime_prompt = build_prompt(
        instance_id=instance_id,
        traces=baseline_traces,
        failure_summary=failure_summary,
        testcase_source=testcase_source,
        related_context=related_context,
        include_runtime=True,
        source_map=source_map,
        frame_context_lines=args.context_lines,
    )

    llm = LLMConnector(provider=args.provider, model=args.model)

    without_runtime_result = run_patch_variant(
        variant_name="without_runtime",
        prompt=no_runtime_prompt,
        llm=llm,
        max_tokens=args.max_tokens,
        reference_pred=reference_pred,
        model_name=args.model,
        test_spec=test_spec,
        client=client,
        run_id=args.run_id,
        run_base=no_runtime_base,
        trace_collector_dir=trace_collector_dir,
        timeout=args.timeout,
        force_rebuild=args.force_rebuild,
        nocache=args.nocache,
        logger=logger,
        artifacts_dir=artifacts_dir,
    )

    with_runtime_result = run_patch_variant(
        variant_name="with_runtime",
        prompt=with_runtime_prompt,
        llm=llm,
        max_tokens=args.max_tokens,
        reference_pred=reference_pred,
        model_name=args.model,
        test_spec=test_spec,
        client=client,
        run_id=args.run_id,
        run_base=with_runtime_base,
        trace_collector_dir=trace_collector_dir,
        timeout=args.timeout,
        force_rebuild=args.force_rebuild,
        nocache=args.nocache,
        logger=logger,
        artifacts_dir=artifacts_dir,
    )

    report = {
        "instance_id": instance_id,
        "framework": baseline_result.get("framework"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline": {
            "run_result": baseline_result,
            "trace_path": str(baseline_trace_path),
            "test_output_path": str(baseline_test_output_path),
            "trace_count": len(baseline_traces),
            "outcome": baseline_outcome,
        },
        "without_runtime": without_runtime_result,
        "with_runtime": with_runtime_result,
        "patches": {
            "reference_swebench": reference_patch,
            "llm_without_runtime": without_runtime_result.get("generated_patch", ""),
            "llm_with_runtime": with_runtime_result.get("generated_patch", ""),
        },
        "comparison": {
            "without_runtime_verdict": build_verdict(
                baseline_outcome,
                without_runtime_result,
            ),
            "with_runtime_verdict": build_verdict(
                baseline_outcome,
                with_runtime_result,
            ),
        },
    }

    report_json_path = artifacts_dir / "comparison_report.json"
    report_md_path = artifacts_dir / "comparison_report.md"

    write_text(report_json_path, json.dumps(report, indent=2, ensure_ascii=False))
    write_text(report_md_path, build_markdown_report(report))

    logger.info("Saved report: %s", report_json_path)
    logger.info("Saved markdown report: %s", report_md_path)

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run SWE-bench debugger patch comparison (without vs with runtime traces)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset", type=str, default="princeton-nlp/SWE-bench_Lite")
    parser.add_argument("--split", type=str, default="test")
    parser.add_argument(
        "--instance_ids",
        nargs="+",
        type=str,
        required=True,
        help="Instance IDs to process",
    )
    parser.add_argument("--predictions_path", type=str, default="gold")
    parser.add_argument(
        "--output_dir",
        type=str,
        default="./debugger_patch_comparison",
        help="Directory for run outputs and reports",
    )
    parser.add_argument("--provider", type=str, default="deepseek")
    parser.add_argument("--model", type=str, default="deepseek-chat")
    parser.add_argument("--max_tokens", type=int, default=2500)
    parser.add_argument("--context_lines", type=int, default=8)
    parser.add_argument("--test_context_lines", type=int, default=25)
    parser.add_argument("--max_context_files", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--force_rebuild", action="store_true")
    parser.add_argument("--nocache", action="store_true")
    parser.add_argument("--run_id", type=str, default="debugger_patch_comparison")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger = setup_logging(args.verbose)

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    trace_collector_dir = REPO_ROOT / "libs" / "tracing"
    if not trace_collector_dir.exists():
        logger.error("Trace collector directory not found: %s", trace_collector_dir)
        return 1

    logger.info("Loading dataset: %s", args.dataset)
    dataset = load_swebench_dataset(args.dataset, args.split)

    instance_id_set = set(args.instance_ids)
    filtered_dataset = [
        instance for instance in dataset if instance[KEY_INSTANCE_ID] in instance_id_set
    ]

    if not filtered_dataset:
        logger.error("No matching instances found for %s", args.instance_ids)
        return 1

    logger.info(
        "Filtered dataset from %d to %d instance(s)",
        len(dataset),
        len(filtered_dataset),
    )

    logger.info("Loading predictions from: %s", args.predictions_path)
    predictions = get_predictions_from_file(args.predictions_path, args.dataset, args.split)
    predictions_by_id = {pred[KEY_INSTANCE_ID]: pred for pred in predictions}

    test_specs = []
    for instance in filtered_dataset:
        instance_id = instance[KEY_INSTANCE_ID]
        if instance_id not in predictions_by_id:
            logger.warning("No prediction found for %s, skipping", instance_id)
            continue
        test_specs.append((make_test_spec(instance), predictions_by_id[instance_id]))

    if not test_specs:
        logger.error("No test specs to run after prediction filtering")
        return 1

    logger.info("Connecting to Docker")
    client = docker.from_env()

    logger.info("Building/checking environment images")
    build_env_images(
        client,
        filtered_dataset,
        force_rebuild=args.force_rebuild,
        max_workers=1,
        namespace=None,
        instance_image_tag="latest",
        env_image_tag="latest",
    )

    all_reports: List[Dict[str, Any]] = []
    for test_spec, reference_pred in test_specs:
        report = process_instance(
            args=args,
            client=client,
            test_spec=test_spec,
            reference_pred=reference_pred,
            trace_collector_dir=trace_collector_dir,
            logger=logger,
            output_dir=output_dir,
        )
        all_reports.append(report)

    summary = {
        "dataset": args.dataset,
        "split": args.split,
        "instance_ids": args.instance_ids,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reports": all_reports,
    }

    summary_path = output_dir / "summary_debugger_patch_comparison.json"
    write_text(summary_path, json.dumps(summary, indent=2, ensure_ascii=False))
    logger.info("Saved summary: %s", summary_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
