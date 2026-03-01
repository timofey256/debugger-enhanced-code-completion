#!/usr/bin/env python3
"""
Manual verification of the trace collection fix.

Since bash is not responding, this script can be run to verify the fixes work.
"""

import sys
import os

print("=" * 70)
print("Django Trace Collection Fix - Manual Verification")
print("=" * 70)

# Step 1: Verify unittest_tracer fix
print("\nStep 1: Testing unittest_tracer fix...")
try:
    sys.path.insert(0, "/home/tymofii/develop/debugger-enhanced-code-completion/swebench-trace-collection/trace_collectors")
    from unittest_tracer import inject_unittest_tracer
    inject_unittest_tracer()
    print("✓ unittest_tracer imports and injects without UnboundLocalError")
except Exception as e:
    print(f"✗ unittest_tracer failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 2: Verify django_tracer_new
print("\nStep 2: Testing django_tracer_new...")
try:
    from django_tracer_new import inject_django_tracer
    inject_django_tracer()
    print("✓ django_tracer_new imports and injects successfully")
except Exception as e:
    print(f"✗ django_tracer_new failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 3: Run a simple unittest test to verify trace capture
print("\nStep 3: Running simple unittest with django_tracer...")
import unittest
import tempfile

# Set output path
output_file = tempfile.mktemp(suffix=".json")
os.environ['AUTO_DEBUG_JSON'] = output_file

class SimpleFailingTest(unittest.TestCase):
    def test_should_fail(self):
        """This test should fail and be captured."""
        self.assertEqual(1, 2, "Intentional failure")
    
    def test_should_error(self):
        """This test should error and be captured."""
        1 / 0
    
    def test_should_pass(self):
        """This test should pass."""
        self.assertEqual(1, 1)

# Run tests
loader = unittest.TestLoader()
suite = loader.loadTestsFromTestCase(SimpleFailingTest)
runner = unittest.TextTestRunner(verbosity=0)
result = runner.run(suite)

# Check results
print(f"\nTests run: {result.testsRun}")
print(f"Failures: {len(result.failures)}")
print(f"Errors: {len(result.errors)}")

# Check trace file
if os.path.exists(output_file):
    import json
    with open(output_file) as f:
        traces = json.load(f)
    
    print(f"\n✓ Trace file created: {output_file}")
    print(f"✓ Traces captured: {len(traces)}")
    
    for i, trace in enumerate(traces, 1):
        print(f"\n  Trace {i}:")
        print(f"    Node: {trace['nodeid']}")
        print(f"    Exception: {trace['exc_type']}")
        print(f"    Message: {trace['message']}")
        print(f"    Frames: {len(trace.get('frames', []))}")
        if trace.get('frames'):
            frame = trace['frames'][0]
            print(f"    First frame: {frame['file']}:{frame['line']} in {frame['func']}")
    
    # Cleanup
    os.remove(output_file)
    
    if len(traces) >= 2:
        print("\n" + "=" * 70)
        print("✓✓✓ SUCCESS: All fixes verified! ✓✓✓")
        print("=" * 70)
        print("\nThe django_tracer monkey-patching approach works correctly.")
        print("You can now run the full SWE-bench trace collection:")
        print()
        print("  python scripts/run_swebench_with_traces.py \\")
        print("      --dataset princeton-nlp/SWE-bench_Lite \\")
        print("      --instance_ids django__django-11583 \\")
        print("      --predictions_path gold \\")
        print("      --output_dir ./traces_test_fixed \\")
        print("      --skip-patch --verbose")
        print()
    else:
        print(f"\n✗ Expected at least 2 traces, got {len(traces)}")
        sys.exit(1)
else:
    print(f"\n✗ Trace file not created: {output_file}")
    sys.exit(1)
