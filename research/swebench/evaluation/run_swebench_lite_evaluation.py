#!/usr/bin/env python3
"""Run debugger patch-comparison evaluation over SWE-bench Lite at dataset scale."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import docker

REPO_ROOT = Path(__file__).resolve().parents[3]

from libs.harness import (
    ComparisonConfig,
    FrameworkDetector,
    InstanceComparison,
    Variant,
)
from libs.llm.connector import LLMConnector
from libs.log import create_logger

from research.swebench.harness.benchmark_index import (
    append_record,
    build_instance_index_record,
    finalize_run_index,
    init_run_index,
    write_run_index,
)
from swebench.harness.constants import KEY_INSTANCE_ID
from swebench.harness.docker_build import build_env_images
from swebench.harness.test_spec.test_spec import make_test_spec
from swebench.harness.utils import get_predictions_from_file, load_swebench_dataset


def resolve_run_id(raw_run_id: str | None) -> str:
    if raw_run_id:
        return raw_run_id
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"swebench_lite_eval_{stamp}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run modular SWE-bench Lite benchmark evaluation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset", type=str, default="princeton-nlp/SWE-bench_Lite")
    parser.add_argument("--split", type=str, default="test")
    parser.add_argument("--predictions_path", type=str, default="gold")
    parser.add_argument("--output_dir", type=str, default="./output/benchmark-runs")
    parser.add_argument("--run_id", type=str, default=None)
    parser.add_argument("--provider", type=str, default="deepseek")
    parser.add_argument("--model", type=str, default="deepseek-chat")
    parser.add_argument("--max_tokens", type=int, default=2500)
    parser.add_argument("--context_lines", type=int, default=8)
    parser.add_argument("--test_context_lines", type=int, default=25)
    parser.add_argument("--max_context_files", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--force_rebuild", action="store_true")
    parser.add_argument("--nocache", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--filter_for",
        nargs="+",
        type=str,
        default=[],
        help="Repository prefixes to FILTER for. Overrides `exclude_repos`!",
    )
    parser.add_argument(
        "--exclude_repos",
        nargs="+",
        type=str,
        default=[],
        help="Repository prefixes to EXCLUDE",
    )
    return parser.parse_args()


def select_instances(
    dataset: List[Dict[str, Any]],
    filter_for: List[str] | None = None,
    exclude_repos: List[str] | None = None,
) -> List[Dict[str, Any]]:
    candidates = dataset
    if filter_for:
        for e in filter_for:
            candidates = [
                i for i in candidates
                if i[KEY_INSTANCE_ID].startswith(e)
            ]
        return list(candidates)

    if exclude_repos:
        for e in exclude_repos:
            candidates = [
                i for i in candidates
                if not i[KEY_INSTANCE_ID].startswith(e)
            ]
    return list(candidates)


def build_test_specs(
    instances: List[Dict[str, Any]],
    predictions_by_id: Dict[str, Dict[str, Any]],
    logger,
) -> List[Tuple[Any, Dict[str, Any]]]:
    items: List[Tuple[Any, Dict[str, Any]]] = []
    for instance in instances:
        instance_id = instance[KEY_INSTANCE_ID]
        prediction = predictions_by_id.get(instance_id)
        if prediction is None:
            logger.warning("No prediction found for %s, skipping", instance_id)
            continue
        items.append((make_test_spec(instance), prediction))
    return items


def build_config(args: argparse.Namespace) -> ComparisonConfig:
    return ComparisonConfig(
        model_name=args.model,
        max_tokens=args.max_tokens,
        context_lines=args.context_lines,
        test_context_lines=args.test_context_lines,
        max_context_files=args.max_context_files,
        timeout=args.timeout,
        force_rebuild=args.force_rebuild,
        nocache=args.nocache,
    )


def main() -> int:
    args = parse_args()
    run_id = resolve_run_id(args.run_id)

    run_root = Path(args.output_dir).resolve() / run_id
    log_path = run_root / "logs" / "run.log"
    logger = create_logger(
        "swebench_lite_evaluation", log_path=log_path, verbose=args.verbose
    )

    logger.info("Run ID: %s", run_id)
    logger.info("Run root: %s", run_root)
    logger.info("Logs file: %s", log_path)

    logger.info("Loading dataset: %s", args.dataset)
    dataset = load_swebench_dataset(args.dataset, args.split)
    selected_instances = select_instances(dataset, args.filter_for, args.exclude_repos)
    logger.info(
        "Selected %d instance(s) from %d total",
        len(selected_instances),
        len(dataset),
    )
    if not selected_instances:
        logger.error("No instances selected for execution")
        return 1

    logger.info("Loading predictions from: %s", args.predictions_path)
    predictions = get_predictions_from_file(
        args.predictions_path, args.dataset, args.split
    )
    predictions_by_id = {pred[KEY_INSTANCE_ID]: pred for pred in predictions}

    test_specs = build_test_specs(selected_instances, predictions_by_id, logger)
    if not test_specs:
        logger.error("No runnable test specs after matching predictions")
        return 1

    logger.info("Connecting to Docker")
    client = docker.from_env()

    logger.info("Building/checking environment images")
    build_env_images(
        client,
        selected_instances,
        force_rebuild=args.force_rebuild,
        max_workers=1,
        namespace=None,
        instance_image_tag="latest",
        env_image_tag="latest",
    )

    trace_collector_dir = REPO_ROOT / "libs" / "tracing"
    if not trace_collector_dir.exists():
        logger.error("Trace collector directory not found: %s", trace_collector_dir)
        return 1

    config = build_config(args)
    llm = LLMConnector(provider=args.provider, model=args.model)
    framework_detector = FrameworkDetector()

    index = init_run_index(
        run_id=run_id,
        dataset=args.dataset,
        split=args.split,
        model=args.model,
        predictions_path=args.predictions_path,
        log_path=log_path,
        total_instances=len(test_specs),
    )
    index_path = run_root / "index" / "instance_status_index.json"
    write_run_index(index_path, index)

    total = len(test_specs)
    for idx, (test_spec, reference_pred) in enumerate(test_specs, start=1):
        instance_id = test_spec.instance_id
        logger.info("[%d/%d] Starting %s", idx, total, instance_id)

        comparison = InstanceComparison(
            test_spec=test_spec,
            reference_pred=reference_pred,
            client=client,
            llm=llm,
            trace_collector_dir=trace_collector_dir,
            output_dir=run_root,
            run_id=run_id,
            config=config,
            logger=logger,
            framework_detector=framework_detector,
        )
        report = comparison.run()
        if report is None:
            logger.error("[%d/%d] Skipped %s due to fatal error", idx, total, instance_id)
            continue
        report_dict = report.to_dict()

        report_path = run_root / "artifacts" / instance_id / "comparison_report.json"
        record = build_instance_index_record(report_dict, report_path=report_path)
        append_record(index, record)
        write_run_index(index_path, index)

        without_status = record["variants"][Variant.WITHOUT_RUNTIME.value]["status"]
        with_status = record["variants"][Variant.WITH_RUNTIME.value]["status"]
        logger.info(
            "[%d/%d] Finished %s (%s=%s, %s=%s)",
            idx,
            total,
            instance_id,
            Variant.WITHOUT_RUNTIME.value,
            without_status,
            Variant.WITH_RUNTIME.value,
            with_status,
        )

    finalize_run_index(index)
    write_run_index(index_path, index)
    logger.info("Dataset run complete")
    logger.info("Index file: %s", index_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
