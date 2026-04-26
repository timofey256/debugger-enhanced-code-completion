#!/usr/bin/env python3
"""
Calculate SWE-bench Lite benchmark metrics from dataset-level index records.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from libs.harness import Status, Variant


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute SWE-bench Lite benchmark metrics from index data",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "index_path",
        help="Path to dataset index file (instance_status_index.json)",
    )
    parser.add_argument(
        "--output-json",
        help="Optional path to write computed metrics JSON",
    )
    return parser.parse_args()


def load_index(path: Path) -> Dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("Index file must contain a JSON object")
    return data


def compute_variant_metrics(records: List[Dict[str, Any]], variant_name: str) -> Dict[str, Any]:
    total = len(records)
    status_counts = Counter()
    reason_counts = Counter()

    for record in records:
        variants = record.get("variants", {})
        if not isinstance(variants, dict):
            continue
        variant = variants.get(variant_name, {})
        if not isinstance(variant, dict):
            continue

        status = str(variant.get("status", Status.UNKNOWN.value))
        status_counts[status] += 1

        if status != Status.PASSED.value:
            reason = variant.get("failure_reason") or "unknown"
            reason_counts[str(reason)] += 1

    success_count = status_counts.get(Status.PASSED.value, 0)
    failure_count = max(total - success_count, 0)
    success_rate = (success_count / total) if total else 0.0
    failure_rate = (failure_count / total) if total else 0.0

    return {
        "total_instances": total,
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": success_rate,
        "failure_rate": failure_rate,
        "status_counts": dict(status_counts),
        "failure_reason_counts": dict(reason_counts),
    }


def compute_metrics(index: Dict[str, Any]) -> Dict[str, Any]:
    records = index.get("records", [])
    if not isinstance(records, list):
        raise ValueError("Index records must be a list")

    return {
        "run_id": index.get("run_id"),
        "dataset": index.get("dataset"),
        "split": index.get("split"),
        "model": index.get("model"),
        "created_at": index.get("created_at"),
        "completed_at": index.get("completed_at"),
        Variant.WITHOUT_RUNTIME.value: compute_variant_metrics(
            records, Variant.WITHOUT_RUNTIME.value
        ),
        Variant.WITH_RUNTIME.value: compute_variant_metrics(
            records, Variant.WITH_RUNTIME.value
        ),
    }


def print_summary(metrics: Dict[str, Any]) -> None:
    print(f"Run ID: {metrics.get('run_id')}")
    print(f"Dataset: {metrics.get('dataset')} [{metrics.get('split')}]")
    print(f"Model: {metrics.get('model')}")
    print("")

    for variant_name in (Variant.WITHOUT_RUNTIME.value, Variant.WITH_RUNTIME.value):
        variant = metrics.get(variant_name, {})
        print(f"== {variant_name} ==")
        print(f"Total instances: {variant.get('total_instances')}")
        print(
            "Success: {}/{} ({:.2%})".format(
                variant.get("success_count"),
                variant.get("total_instances"),
                variant.get("success_rate", 0.0),
            )
        )
        print(
            "Failure: {}/{} ({:.2%})".format(
                variant.get("failure_count"),
                variant.get("total_instances"),
                variant.get("failure_rate", 0.0),
            )
        )
        print("Failure reasons:")
        reasons = variant.get("failure_reason_counts", {})
        if not reasons:
            print("  - none")
        else:
            for reason, count in sorted(reasons.items(), key=lambda item: (-item[1], item[0])):
                print(f"  - {reason}: {count}")
        print("")


def main() -> int:
    args = parse_args()
    index_path = Path(args.index_path).resolve()
    if not index_path.exists():
        raise FileNotFoundError(f"Index path not found: {index_path}")

    index = load_index(index_path)
    metrics = compute_metrics(index)
    print_summary(metrics)

    if args.output_json:
        output_path = Path(args.output_json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(metrics, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Wrote metrics JSON: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
