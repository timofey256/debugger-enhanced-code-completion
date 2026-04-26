#!/usr/bin/env python3
"""Run SWE-bench evaluation with trace collection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import docker

REPO_ROOT = Path(__file__).resolve().parents[3]

from libs.harness import (
    FrameworkDetector,
    TraceOutputManager,
    TracedInstanceRunner,
)
from libs.log import create_logger

from swebench.harness.constants import KEY_INSTANCE_ID
from swebench.harness.docker_build import build_env_images
from swebench.harness.test_spec.test_spec import make_test_spec
from swebench.harness.utils import (
    get_predictions_from_file,
    load_swebench_dataset,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run SWE-bench evaluation with trace collection",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset", type=str, default="princeton-nlp/SWE-bench_Lite")
    parser.add_argument("--split", type=str, default="test")
    parser.add_argument("--instance_ids", nargs="+", type=str)
    parser.add_argument("--predictions_path", type=str, default="gold")
    parser.add_argument("--output_dir", type=str, default="output/traces/swebench")
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--force_rebuild", action="store_true")
    parser.add_argument("--nocache", action="store_true")
    parser.add_argument("--run_id", type=str, default="trace_collection")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--skip-patch", dest="skip_patch", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger = create_logger("swebench_trace_collection", verbose=args.verbose)

    logger.info("=" * 70)
    logger.info("SWE-bench Trace Collection")
    logger.info("=" * 70)
    logger.info("Dataset: %s", args.dataset)
    logger.info("Output directory: %s", args.output_dir)
    logger.info("Run ID: %s", args.run_id)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trace_collector_dir = REPO_ROOT / "libs" / "tracing"
    if not trace_collector_dir.exists():
        logger.error("Trace collector directory not found: %s", trace_collector_dir)
        return 1
    logger.info("Trace collectors: %s", trace_collector_dir)

    logger.info("Loading dataset: %s", args.dataset)
    try:
        dataset = load_swebench_dataset(args.dataset, args.split)
        if args.instance_ids:
            instance_ids_set = set(args.instance_ids)
            dataset = [
                instance
                for instance in dataset
                if instance[KEY_INSTANCE_ID] in instance_ids_set
            ]
    except Exception as exc:
        logger.error("Failed to load dataset: %s", exc)
        return 1

    if not dataset:
        logger.error("No instances found in dataset")
        return 1
    logger.info("Loaded %d instances", len(dataset))

    logger.info("Loading predictions from: %s", args.predictions_path)
    try:
        predictions = get_predictions_from_file(
            args.predictions_path, args.dataset, args.split
        )
        predictions = {pred[KEY_INSTANCE_ID]: pred for pred in predictions}
    except Exception as exc:
        logger.error("Failed to load predictions: %s", exc)
        return 1
    logger.info("Loaded predictions for %d instances", len(predictions))

    test_specs = []
    for instance in dataset:
        instance_id = instance[KEY_INSTANCE_ID]
        if instance_id not in predictions:
            logger.warning("No prediction found for %s, skipping", instance_id)
            continue
        test_specs.append(make_test_spec(instance))
    logger.info("Created %d test specifications", len(test_specs))

    logger.info("Connecting to Docker...")
    try:
        client = docker.from_env()
    except Exception as exc:
        logger.error("Failed to connect to Docker: %s", exc)
        return 1

    if not args.force_rebuild:
        logger.info("Building/checking environment images...")
        try:
            build_env_images(
                client,
                dataset,
                force_rebuild=args.force_rebuild,
                max_workers=1,
                namespace=None,
                instance_image_tag="latest",
                env_image_tag="latest",
            )
        except Exception as exc:
            logger.error("Failed to build environment images: %s", exc)
            return 1

    output_manager = TraceOutputManager(output_dir)
    framework_detector = FrameworkDetector()

    logger.info("\n" + "=" * 70)
    logger.info("Starting trace collection")
    logger.info("=" * 70)

    results = []
    for test_spec in test_specs:
        instance_id = test_spec.instance_id
        pred = predictions[instance_id]
        runner = TracedInstanceRunner(
            client=client,
            test_spec=test_spec,
            run_id=args.run_id,
            trace_collector_dir=trace_collector_dir,
            output_manager=output_manager,
            framework_detector=framework_detector,
            logger=logger,
            timeout=args.timeout,
            force_rebuild=args.force_rebuild,
            nocache=args.nocache,
        )
        result = runner.run(pred, skip_patch=args.skip_patch)
        results.append(result.to_dict())

    logger.info("\n" + "=" * 70)
    logger.info("Trace Collection Summary")
    logger.info("=" * 70)
    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    logger.info("Total instances: %d", len(results))
    logger.info("Successful: %d", len(successful))
    logger.info("Failed: %d", len(failed))

    if successful:
        logger.info("\nSuccessful instances:")
        for r in successful:
            logger.info(
                "  %s: %d failures captured (%s)",
                r["instance_id"],
                r.get("num_failures", 0),
                r.get("framework", "unknown"),
            )
    if failed:
        logger.info("\nFailed instances:")
        for r in failed:
            logger.info("  %s: %s", r["instance_id"], r.get("error", "Unknown error"))

    summary_file = output_dir / f"summary_{args.run_id}.json"
    summary_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    logger.info("\nResults summary saved to: %s", summary_file)

    if failed:
        logger.error("\nTrace collection failed for some instances. See errors above.")
        return 1
    logger.info("\nAll instances completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
