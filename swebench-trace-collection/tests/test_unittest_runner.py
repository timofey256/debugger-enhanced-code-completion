#!/usr/bin/env python
"""
Test runner for unittest tracer verification.

This demonstrates how to use DebugTestResult with unittest.
"""

import sys
import os
import unittest
from pathlib import Path
from io import StringIO

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from trace_collectors.unittest_tracer import DebugTestResult
from tests.sample_failing_tests import SampleTests


def main():
    """Run sample tests with DebugTestResult."""
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(SampleTests)

    # Create custom runner with DebugTestResult
    runner = unittest.TextTestRunner(
        resultclass=DebugTestResult,
        stream=StringIO(),  # Suppress output
        verbosity=0
    )

    # Run tests
    print("Running sample tests with DebugTestResult...")
    result = runner.run(suite)

    # Print results
    print(f"\nTests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Debug traces captured: {len(result.debug_store)}")

    # Show captured traces
    if result.debug_store:
        print("\nCaptured traces:")
        for i, trace in enumerate(result.debug_store, 1):
            print(f"\n{i}. {trace['nodeid']}")
            print(f"   Exception: {trace['exc_type']}: {trace['message']}")
            print(f"   Frames: {len(trace['frames'])}")

            # Show first frame
            if trace['frames']:
                frame = trace['frames'][0]
                print(f"   First frame: {frame['func']} at {Path(frame['file']).name}:{frame['line']}")
                print(f"   Locals: {list(frame['locals'].keys())}")

    # Check output file was created
    output_file = Path("auto_debug.json")
    if output_file.exists():
        print(f"\n✓ Output file created: {output_file}")
        print(f"  Size: {output_file.stat().st_size} bytes")

        # Clean up
        output_file.unlink()
        print("  (Cleaned up test file)")
    else:
        print("\n✗ Output file was not created")

    return 0 if len(result.debug_store) == 2 else 1  # Expect 2 failures


if __name__ == "__main__":
    sys.exit(main())
