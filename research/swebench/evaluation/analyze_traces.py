#!/usr/bin/env python
"""
Quick analysis of collected traces.
"""

import json
from pathlib import Path
from collections import defaultdict

def analyze_traces(trace_file):
    """Analyze a trace file and print statistics."""
    with open(trace_file) as f:
        data = json.load(f)

    print(f"\n{'='*70}")
    print(f"Trace Analysis: {trace_file.name}")
    print(f"{'='*70}\n")

    print(f"Total test failures captured: {len(data)}")

    # Count by exception type
    exc_types = defaultdict(int)
    total_frames = 0
    failures_with_frames = 0

    for entry in data:
        exc_type = entry.get('exc_type', 'Unknown')
        exc_types[exc_type] += 1

        frames = entry.get('frames', [])
        total_frames += len(frames)
        if frames:
            failures_with_frames += 1

    print(f"Failures with stack frames: {failures_with_frames}")
    print(f"Total stack frames collected: {total_frames}")
    print(f"Average frames per failure: {total_frames/len(data):.1f}")

    print(f"\nException Types:")
    for exc_type, count in sorted(exc_types.items(), key=lambda x: x[1], reverse=True):
        pct = 100 * count / len(data)
        print(f"  {exc_type:30s}: {count:3d} ({pct:5.1f}%)")

    # Show sample trace
    print(f"\nSample Trace (first failure with frames):")
    for entry in data:
        if entry.get('frames'):
            print(f"\nTest: {entry['nodeid']}")
            print(f"Exception: {entry['exc_type']}: {entry['message']}")
            print(f"Stack frames: {len(entry['frames'])}")

            if entry['frames']:
                frame = entry['frames'][-1]  # Last frame (closest to error)
                print(f"\nError location:")
                print(f"  File: {Path(frame['file']).name}")
                print(f"  Line: {frame['line']}")
                print(f"  Function: {frame['func']}")
                print(f"  Local variables: {len(frame['locals'])}")

                # Show a few locals
                print(f"\n  Sample locals:")
                for key, value in list(frame['locals'].items())[:3]:
                    value_preview = value[:60] + "..." if len(value) > 60 else value
                    print(f"    {key}: {value_preview}")

            break

    print(f"\n{'='*70}\n")

if __name__ == "__main__":
    trace_file = Path("output/traces/jsonschema/auto_debug.json")
    if trace_file.exists():
        analyze_traces(trace_file)
    else:
        print(f"Trace file not found: {trace_file}")
