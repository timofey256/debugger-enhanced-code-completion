#!/usr/bin/env python3
"""
Run SWE-bench evaluation with trace collection.

This script wraps SWE-bench's evaluation harness to collect detailed stack traces
from failing tests.

Usage:
    python run_swebench_with_traces.py \
        --dataset princeton-nlp/SWE-bench_Lite \
        --instance_ids django__django-11583 \
        --predictions_path gold \
        --output_dir ./traces
"""

import argparse
import docker
import json
import logging
import sys
from pathlib import Path

# Add SWE-bench to path
sys.path.insert(0, "/home/tymofii/develop/SWE-bench")
sys.path.insert(0, str(Path(__file__).parent.parent))  # Add swebench-trace-collection to path

from swebench.harness.utils import (
    load_swebench_dataset,
    get_predictions_from_file,
)
from swebench.harness.test_spec.test_spec import make_test_spec
from swebench.harness.docker_build import build_env_images
from swebench.harness.constants import KEY_INSTANCE_ID

from swebench_integration.wrapper import run_instance_with_traces


def setup_logging(verbose: bool = False):
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Run SWE-bench evaluation with trace collection",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Dataset arguments
    parser.add_argument(
        "--dataset",
        type=str,
        default="princeton-nlp/SWE-bench_Lite",
        help="SWE-bench dataset name",
    )
    parser.add_argument(
        "--split",
        type=str,
        default="test",
        help="Dataset split to use",
    )
    parser.add_argument(
        "--instance_ids",
        nargs="+",
        type=str,
        help="Specific instance IDs to run (space-separated). If not provided, runs all instances.",
    )

    # Prediction arguments
    parser.add_argument(
        "--predictions_path",
        type=str,
        default="gold",
        help="Path to predictions file (JSONL/JSON) or 'gold' for ground truth patches",
    )

    # Output arguments
    parser.add_argument(
        "--output_dir",
        type=str,
        default="./traces",
        help="Output directory for trace files",
    )

    # Runtime arguments
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Timeout for test execution (seconds)",
    )
    parser.add_argument(
        "--force_rebuild",
        action="store_true",
        help="Force rebuild of Docker images",
    )
    parser.add_argument(
        "--nocache",
        action="store_true",
        help="Don't use cache when building images",
    )
    parser.add_argument(
        "--run_id",
        type=str,
        default="trace_collection",
        help="Run ID for this execution",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--skip-patch",
        action="store_true",
        help="Skip patch application (useful for collecting traces from original failing tests)",
    )

    args = parser.parse_args()

    # Set up logging
    logger = setup_logging(args.verbose)

    logger.info("="*70)
    logger.info("SWE-bench Trace Collection")
    logger.info("="*70)
    logger.info(f"Dataset: {args.dataset}")
    logger.info(f"Output directory: {args.output_dir}")
    logger.info(f"Run ID: {args.run_id}")

    # Set up paths
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trace_collector_dir = Path(__file__).parent.parent / "trace_collectors"
    if not trace_collector_dir.exists():
        logger.error(f"Trace collector directory not found: {trace_collector_dir}")
        return 1

    logger.info(f"Trace collectors: {trace_collector_dir}")

    # Load dataset
    logger.info(f"Loading dataset: {args.dataset}")
    logger.debug(f"Instance IDs filter: {args.instance_ids}")
    try:
        dataset = load_swebench_dataset(
            args.dataset,
            args.split,
        )

        # Filter to specified instance_ids if provided
        if args.instance_ids:
            logger.info(f"Filtering dataset to {len(args.instance_ids)} instance(s): {args.instance_ids}")
            instance_ids_set = set(args.instance_ids)
            original_count = len(dataset)
            dataset = [
                instance for instance in dataset
                if instance[KEY_INSTANCE_ID] in instance_ids_set
            ]
            logger.info(f"Filtered from {original_count} to {len(dataset)} instance(s)")
        else:
            logger.info("No instance_ids filter specified, using all instances")
    except Exception as e:
        logger.error(f"Failed to load dataset: {e}")
        return 1

    if not dataset:
        logger.error("No instances found in dataset")
        return 1

    logger.info(f"Loaded {len(dataset)} instances")

    # Load predictions
    logger.info(f"Loading predictions from: {args.predictions_path}")
    try:
        predictions = get_predictions_from_file(
            args.predictions_path,
            args.dataset,
            args.split,
        )
        predictions = {pred[KEY_INSTANCE_ID]: pred for pred in predictions}
    except Exception as e:
        logger.error(f"Failed to load predictions: {e}")
        return 1

    logger.info(f"Loaded predictions for {len(predictions)} instances")

    # Create TestSpecs for all instances
    logger.info("Creating test specifications...")
    test_specs = []
    for instance in dataset:
        instance_id = instance[KEY_INSTANCE_ID]

        if instance_id not in predictions:
            logger.warning(f"No prediction found for {instance_id}, skipping")
            continue

        test_spec = make_test_spec(instance)
        test_specs.append(test_spec)

    logger.info(f"Created {len(test_specs)} test specifications")

    # Initialize Docker client
    logger.info("Connecting to Docker...")
    try:
        client = docker.from_env()
    except Exception as e:
        logger.error(f"Failed to connect to Docker: {e}")
        return 1

    # Build environment images (if not already built)
    if not args.force_rebuild:
        logger.info("Building/checking environment images...")
        try:
            build_env_images(
                client,
                dataset,
                force_rebuild=args.force_rebuild,
                max_workers=1,  # Sequential for now
                namespace=None,
                instance_image_tag="latest",
                env_image_tag="latest",
            )
        except Exception as e:
            logger.error(f"Failed to build environment images: {e}")
            return 1

    # Run trace collection for each instance
    logger.info("\n" + "="*70)
    logger.info("Starting trace collection")
    logger.info("="*70)

    results = []
    for test_spec in test_specs:
        instance_id = test_spec.instance_id
        pred = predictions[instance_id]

        # Run instance with trace collection
        result = run_instance_with_traces(
            test_spec=test_spec,
            pred=pred,
            client=client,
            run_id=args.run_id,
            trace_output_base=str(output_dir),
            trace_collector_dir=str(trace_collector_dir),
            timeout=args.timeout,
            force_rebuild=args.force_rebuild,
            nocache=args.nocache,
            skip_patch=args.skip_patch,
            logger=logger,
        )

        results.append(result)

    # Print summary
    logger.info("\n" + "="*70)
    logger.info("Trace Collection Summary")
    logger.info("="*70)

    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]

    logger.info(f"Total instances: {len(results)}")
    logger.info(f"Successful: {len(successful)}")
    logger.info(f"Failed: {len(failed)}")

    if successful:
        logger.info("\nSuccessful instances:")
        for result in successful:
            logger.info(f"  ✓ {result['instance_id']}: "
                       f"{result.get('num_failures', 0)} failures captured "
                       f"({result.get('framework', 'unknown')})")

    if failed:
        logger.info("\nFailed instances:")
        for result in failed:
            logger.info(f"  ✗ {result['instance_id']}: {result.get('error', 'Unknown error')}")

    # Save results summary
    summary_file = output_dir / f"summary_{args.run_id}.json"
    with open(summary_file, 'w') as f:
        json.dump(results, f, indent=2)
    logger.info(f"\nResults summary saved to: {summary_file}")

    # Exit with error if any instances failed (user requested strict mode)
    if failed:
        logger.error("\nTrace collection failed for some instances. See errors above.")
        return 1

    logger.info("\n✓ All instances completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
