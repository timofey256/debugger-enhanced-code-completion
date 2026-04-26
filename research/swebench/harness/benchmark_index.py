"""
Helpers for dataset-level SWE-bench benchmarking run index records.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from libs.harness import Status, Variant


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _excerpt(value: Any, limit: int = 500) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def classify_failure_reason(
    status: str,
    summary_line: Optional[str],
    run_error: Optional[str],
) -> Optional[str]:
    if status == Status.PASSED.value:
        return None

    combined = f"{summary_line or ''} {run_error or ''}".lower()

    if status == Status.APPLY_FAILED.value:
        return "patch_apply_failed"

    if status == Status.NOT_RUN.value:
        if "no unified diff" in combined:
            return "no_patch_generated"
        if "unauthorized" in combined or "401" in combined:
            return "llm_request_failed"
        return "not_run"

    if status == Status.FAILED.value:
        if "timed out" in combined or "timeout" in combined:
            return "test_timeout"
        return "tests_failed"

    return "unknown"


def normalize_variant_record(variant_report: Dict[str, Any]) -> Dict[str, Any]:
    outcome = variant_report.get("outcome", {})
    if not isinstance(outcome, dict):
        outcome = {}

    run_result = variant_report.get("run_result", {})
    if not isinstance(run_result, dict):
        run_result = {}

    status = str(outcome.get("status", Status.NOT_RUN.value))
    summary_line = str(outcome.get("summary_line", ""))
    run_error = str(run_result.get("error", ""))

    return {
        "status": status,
        "failure_count": outcome.get("failure_count"),
        "ran_tests": outcome.get("ran_tests"),
        "summary_line": summary_line,
        "failure_reason": classify_failure_reason(status, summary_line, run_error),
        "raw_error_excerpt": _excerpt(run_error or summary_line or run_result.get("traceback", "")),
        "prompt_path": variant_report.get("prompt_path"),
        "response_path": variant_report.get("response_path"),
        "patch_path": variant_report.get("patch_path"),
        "test_output_path": variant_report.get("test_output_path"),
    }


def normalize_baseline_record(baseline_report: Dict[str, Any]) -> Dict[str, Any]:
    outcome = baseline_report.get("outcome", {})
    if not isinstance(outcome, dict):
        outcome = {}

    run_result = baseline_report.get("run_result", {})
    if not isinstance(run_result, dict):
        run_result = {}

    status = str(outcome.get("status", Status.UNKNOWN.value))
    summary_line = str(outcome.get("summary_line", ""))
    run_error = str(run_result.get("error", ""))

    return {
        "status": status,
        "failure_count": outcome.get("failure_count"),
        "ran_tests": outcome.get("ran_tests"),
        "summary_line": summary_line,
        "failure_reason": classify_failure_reason(status, summary_line, run_error),
        "raw_error_excerpt": _excerpt(run_error or summary_line or run_result.get("traceback", "")),
        "trace_path": baseline_report.get("trace_path"),
        "test_output_path": baseline_report.get("test_output_path"),
    }


def build_instance_index_record(
    report: Dict[str, Any],
    report_path: Path,
) -> Dict[str, Any]:
    baseline = report.get("baseline", {})
    without_runtime = report.get(Variant.WITHOUT_RUNTIME.value, {})
    with_runtime = report.get(Variant.WITH_RUNTIME.value, {})

    if not isinstance(baseline, dict):
        baseline = {}
    if not isinstance(without_runtime, dict):
        without_runtime = {}
    if not isinstance(with_runtime, dict):
        with_runtime = {}

    return {
        "instance_id": report.get("instance_id"),
        "framework": report.get("framework"),
        "recorded_at": now_utc_iso(),
        "artifact_report_path": str(report_path),
        "baseline": normalize_baseline_record(baseline),
        "variants": {
            Variant.WITHOUT_RUNTIME.value: normalize_variant_record(without_runtime),
            Variant.WITH_RUNTIME.value: normalize_variant_record(with_runtime),
        },
    }


def init_run_index(
    run_id: str,
    dataset: str,
    split: str,
    model: str,
    predictions_path: str,
    log_path: Path,
    total_instances: int,
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "dataset": dataset,
        "split": split,
        "model": model,
        "predictions_path": predictions_path,
        "created_at": now_utc_iso(),
        "completed_at": None,
        "log_path": str(log_path),
        "total_instances": total_instances,
        "records": [],
    }


def append_record(index: Dict[str, Any], record: Dict[str, Any]) -> None:
    records = index.setdefault("records", [])
    if isinstance(records, list):
        records.append(record)


def finalize_run_index(index: Dict[str, Any]) -> None:
    index["completed_at"] = now_utc_iso()


def write_run_index(index_path: Path, index: Dict[str, Any]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
