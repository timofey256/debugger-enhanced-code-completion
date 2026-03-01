#!/usr/bin/env python3
"""
Test that django_tracer_new.py works correctly by simulating Django test execution.
"""

import sys
import os
import tempfile
import unittest

# Add trace_collectors to path
sys.path.insert(0, "/home/tymofii/develop/debugger-enhanced-code-completion/swebench-trace-collection/trace_collectors")

# Set environment variable
os.environ['AUTO_DEBUG_JSON'] = '/tmp/test_django_trace.json'

# Import and inject the tracer
from django_tracer_new import inject_django_tracer

print("=" * 70)
print("Testing Django Tracer Injection")
print("=" * 70)

# Inject the tracer
inject_django_tracer()

# Create a simple failing test
class TestExample(unittest.TestCase):
    def test_failure(self):
        """Test that should fail."""
        self.assertEqual(1, 2, "Expected failure")
    
    def test_error(self):
        """Test that should error."""
        raise ValueError("Expected error")
    
    def test_pass(self):
        """Test that should pass."""
        self.assertEqual(1, 1)

# Run tests
if __name__ == '__main__':
    # Create a test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestExample)
    
    # Run with a standard TestRunner
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Check if trace file was created
    print("\n" + "=" * 70)
    print("Checking Results")
    print("=" * 70)
    
    trace_file = os.environ['AUTO_DEBUG_JSON']
    if os.path.exists(trace_file):
        import json
        with open(trace_file) as f:
            traces = json.load(f)
        
        print(f"✓ Trace file created: {trace_file}")
        print(f"✓ Number of failures captured: {len(traces)}")
        
        for i, trace in enumerate(traces, 1):
            print(f"\n  Trace {i}:")
            print(f"    Node: {trace['nodeid']}")
            print(f"    Exception: {trace['exc_type']}")
            print(f"    Message: {trace['message']}")
            print(f"    Frames: {len(trace['frames'])}")
        
        if len(traces) >= 2:
            print("\n✓ SUCCESS: Django tracer works correctly!")
            sys.exit(0)
        else:
            print("\n✗ FAILURE: Expected at least 2 traces, got", len(traces))
            sys.exit(1)
    else:
        print(f"✗ FAILURE: Trace file not created: {trace_file}")
        sys.exit(1)
