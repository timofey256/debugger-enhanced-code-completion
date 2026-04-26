#!/usr/bin/env python3
"""
Validation script for collected traces.

Checks that traces have:
- Valid JSON format
- Required fields present
- Non-empty stack frames for failures
- Serializable local variables
"""

import argparse
import json
from pathlib import Path
import sys


def validate_trace_file(trace_file: Path) -> tuple[bool, list[str]]:
    """
    Validate a single trace file.

    Returns:
        (is_valid, list_of_errors)
    """
    errors = []

    # Check file exists
    if not trace_file.exists():
        return False, ["File does not exist"]

    # Check JSON is valid
    try:
        data = json.loads(trace_file.read_text())
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON: {e}"]

    # Check format (should be list of test failures)
    if not isinstance(data, list):
        errors.append("Expected list of test failures")
        return False, errors

    # Validate each test failure entry
    for i, entry in enumerate(data):
        # Check required fields
        required_fields = ["nodeid", "exc_type", "message", "frames"]
        for field in required_fields:
            if field not in entry:
                errors.append(f"Entry {i}: Missing field '{field}'")

        # Check frames is non-empty
        if "frames" in entry:
            if not isinstance(entry["frames"], list):
                errors.append(f"Entry {i}: 'frames' should be a list")
            elif len(entry["frames"]) == 0:
                errors.append(f"Entry {i}: 'frames' is empty")
            else:
                # Validate frame structure
                for j, frame in enumerate(entry["frames"]):
                    frame_fields = ["file", "line", "func", "locals"]
                    for field in frame_fields:
                        if field not in frame:
                            errors.append(
                                f"Entry {i}, frame {j}: Missing field '{field}'"
                            )

    is_valid = len(errors) == 0
    return is_valid, errors


def main():
    parser = argparse.ArgumentParser(
        description="Validate collected trace files"
    )

    parser.add_argument(
        "traces_dir",
        help="Directory containing trace files"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed error messages"
    )

    args = parser.parse_args()

    traces_dir = Path(args.traces_dir)

    if not traces_dir.exists():
        print(f"Error: Directory not found: {traces_dir}")
        return 1

    # Find all trace files
    trace_files = list(traces_dir.rglob("auto_debug.json"))

    if len(trace_files) == 0:
        print(f"No trace files found in {traces_dir}")
        return 1

    print(f"Validating {len(trace_files)} trace files...")

    # Validate each file
    results = {
        "total": len(trace_files),
        "valid": 0,
        "invalid": 0,
        "errors": []
    }

    for trace_file in trace_files:
        is_valid, errors = validate_trace_file(trace_file)

        if is_valid:
            results["valid"] += 1
        else:
            results["invalid"] += 1
            results["errors"].append({
                "file": str(trace_file),
                "errors": errors
            })

            if args.verbose:
                print(f"\n✗ {trace_file.parent.name}:")
                for error in errors:
                    print(f"  - {error}")

    # Print summary
    print(f"\n{'='*60}")
    print(f"Validation Summary")
    print(f"{'='*60}")
    print(f"Total files: {results['total']}")
    print(f"Valid: {results['valid']} ({100*results['valid']/results['total']:.1f}%)")
    print(f"Invalid: {results['invalid']} ({100*results['invalid']/results['total']:.1f}%)")

    if results['invalid'] > 0 and not args.verbose:
        print(f"\nRun with --verbose to see detailed errors")

    print(f"{'='*60}\n")

    return 0 if results['invalid'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
