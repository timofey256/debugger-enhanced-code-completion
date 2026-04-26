#!/usr/bin/env python3
"""
Generate coverage statistics and reports from collected traces.
"""

import argparse
import json
from pathlib import Path
from collections import defaultdict
import sys


def generate_report(traces_dir: Path):
    """Generate comprehensive report on trace collection."""

    # Initialize statistics
    stats = {
        "total_instances": 0,
        "instances_with_traces": 0,
        "total_test_failures": 0,
        "by_framework": defaultdict(lambda: {
            "instances": 0,
            "failures": 0
        }),
        "by_exception_type": defaultdict(int),
        "instances_by_failure_count": defaultdict(int)
    }

    # Scan all instance directories
    for instance_dir in traces_dir.iterdir():
        if not instance_dir.is_dir():
            continue

        stats["total_instances"] += 1

        trace_file = instance_dir / "auto_debug.json"
        if not trace_file.exists():
            continue

        stats["instances_with_traces"] += 1

        try:
            trace_data = json.loads(trace_file.read_text())

            num_failures = len(trace_data) if isinstance(trace_data, list) else 1
            stats["total_test_failures"] += num_failures
            stats["instances_by_failure_count"][num_failures] += 1

            # Count exception types
            for entry in trace_data:
                exc_type = entry.get("exc_type", "Unknown")
                stats["by_exception_type"][exc_type] += 1

        except Exception as e:
            print(f"Warning: Error processing {instance_dir.name}: {e}")

    # Print report
    print(f"\n{'='*70}")
    print(f"SWE-bench Trace Collection Report")
    print(f"{'='*70}\n")

    print(f"Overall Statistics:")
    print(f"  Total instances processed: {stats['total_instances']}")
    print(f"  Instances with traces: {stats['instances_with_traces']}")

    if stats['total_instances'] > 0:
        success_rate = 100 * stats['instances_with_traces'] / stats['total_instances']
        print(f"  Success rate: {success_rate:.1f}%")

    print(f"  Total test failures captured: {stats['total_test_failures']}")

    if stats['instances_with_traces'] > 0:
        avg_failures = stats['total_test_failures'] / stats['instances_with_traces']
        print(f"  Average failures per instance: {avg_failures:.1f}")

    # Exception types
    print(f"\nTop Exception Types:")
    sorted_exceptions = sorted(
        stats['by_exception_type'].items(),
        key=lambda x: x[1],
        reverse=True
    )
    for exc_type, count in sorted_exceptions[:10]:
        pct = 100 * count / stats['total_test_failures'] if stats['total_test_failures'] > 0 else 0
        print(f"  {exc_type}: {count} ({pct:.1f}%)")

    # Failure count distribution
    print(f"\nFailures per Instance Distribution:")
    sorted_counts = sorted(stats['instances_by_failure_count'].items())
    for num_failures, num_instances in sorted_counts[:10]:
        print(f"  {num_failures} failure(s): {num_instances} instances")

    print(f"\n{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Generate report on collected traces"
    )

    parser.add_argument(
        "traces_dir",
        help="Directory containing trace files"
    )

    parser.add_argument(
        "--output",
        help="Save report to JSON file"
    )

    args = parser.parse_args()

    traces_dir = Path(args.traces_dir)

    if not traces_dir.exists():
        print(f"Error: Directory not found: {traces_dir}")
        return 1

    generate_report(traces_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
