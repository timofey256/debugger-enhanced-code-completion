#!/usr/bin/env python3
"""
Main CLI script for collecting traces from SWE-bench dataset.

Usage:
    python collect_swebench_traces.py --dataset princeton-nlp/SWE-bench_Lite
    python collect_swebench_traces.py --instances instance1 instance2
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from research.swebench.harness.framework_detector import FrameworkDetector
from research.swebench.harness.volume_manager import TraceOutputManager
from research.swebench.harness.instance_processor import process_instance
from research.swebench.harness.trace_aggregator import TraceAggregator


def main():
    parser = argparse.ArgumentParser(
        description="Collect stack traces from SWE-bench test failures"
    )

    parser.add_argument(
        "--dataset",
        default="princeton-nlp/SWE-bench_Lite",
        help="Hugging Face dataset name"
    )

    parser.add_argument(
        "--instances",
        nargs="+",
        help="Specific instance IDs to process"
    )

    parser.add_argument(
        "--output-dir",
        default="output/traces/swebench",
        help="Output directory for traces"
    )

    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Number of parallel workers"
    )

    parser.add_argument(
        "--no-aggregate",
        action="store_true",
        help="Skip aggregation step"
    )

    args = parser.parse_args()

    print(f"Loading dataset: {args.dataset}")

    # Load dataset
    try:
        from datasets import load_dataset
        dataset = load_dataset(args.dataset, split='test')
        print(f"Loaded {len(dataset)} instances")
    except Exception as e:
        print(f"Error loading dataset: {e}")
        return 1

    # Filter to specific instances if requested
    if args.instances:
        dataset = [
            instance for instance in dataset
            if instance['instance_id'] in args.instances
        ]
        print(f"Filtered to {len(dataset)} instances")

    # Detect frameworks
    print("Detecting frameworks...")
    detector = FrameworkDetector()
    framework_map = detector.batch_detect(dataset)

    # Set up output management
    output_manager = TraceOutputManager(args.output_dir)

    # Process instances
    print(f"Processing instances with {args.max_workers} workers...")
    results = []

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = []

        for instance in dataset:
            instance_id = instance['instance_id']
            framework = framework_map.get(instance_id, "pytest")

            future = executor.submit(
                process_instance,
                instance,
                framework,
                args.output_dir
            )
            futures.append((instance_id, future))

        # Collect results
        for instance_id, future in futures:
            try:
                result = future.result()
                results.append(result)

                if result.success:
                    print(f"✓ {instance_id} ({result.framework}): {result.num_failures} failures")
                else:
                    print(f"✗ {instance_id} ({result.framework}): {result.error}")

            except Exception as e:
                print(f"✗ {instance_id}: Exception - {e}")

    # Print summary
    print_summary(results)

    # Aggregate traces
    if not args.no_aggregate:
        print("\nAggregating traces...")
        aggregator = TraceAggregator(args.output_dir)
        aggregator.create_unified_dataset()

        stats = aggregator.generate_statistics()
        print(f"\nStatistics:")
        print(f"  Total instances: {stats['total_instances']}")
        print(f"  Successful: {stats['successful']}")
        print(f"  Failed: {stats['failed']}")
        print(f"  Total test failures captured: {stats['total_failures']}")

    return 0


def print_summary(results):
    """Print summary of collection results."""
    total = len(results)
    successful = sum(1 for r in results if r.success)
    failed = total - successful

    print(f"\n{'='*60}")
    print(f"Collection Summary")
    print(f"{'='*60}")
    print(f"Total instances: {total}")
    print(f"Successful: {successful} ({100*successful/total:.1f}%)")
    print(f"Failed: {failed} ({100*failed/total:.1f}%)")

    # Group by framework
    by_framework = {}
    for result in results:
        framework = result.framework
        if framework not in by_framework:
            by_framework[framework] = {"success": 0, "fail": 0}

        if result.success:
            by_framework[framework]["success"] += 1
        else:
            by_framework[framework]["fail"] += 1

    print(f"\nBy framework:")
    for framework, counts in by_framework.items():
        total_fw = counts["success"] + counts["fail"]
        success_rate = 100 * counts["success"] / total_fw if total_fw > 0 else 0
        print(f"  {framework}: {counts['success']}/{total_fw} ({success_rate:.1f}%)")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    sys.exit(main())
