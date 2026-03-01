#!/bin/bash
# Test script to validate the django tracer fixes

set -e

echo "========================================================================"
echo "Django Trace Collection Fix - Validation Script"
echo "========================================================================"
echo ""

# Test 1: Verify unittest_tracer fix (UnboundLocalError)
echo "Test 1: Verifying unittest_tracer fix..."
cd /home/tymofii/develop/debugger-enhanced-code-completion/swebench-trace-collection
python3 -c "
import sys
sys.path.insert(0, 'trace_collectors')
from unittest_tracer import inject_unittest_tracer
inject_unittest_tracer()
print('✓ No UnboundLocalError - unittest_tracer fix verified')
"

# Test 2: Test django_tracer_new with simple unittest
echo ""
echo "Test 2: Testing django_tracer_new with simple unittest..."
python3 test_django_tracer.py

# Test 3: Run full SWE-bench test
echo ""
echo "Test 3: Running full SWE-bench trace collection..."
cd /home/tymofii/develop/debugger-enhanced-code-completion
python scripts/run_swebench_with_traces.py \
    --dataset princeton-nlp/SWE-bench_Lite \
    --instance_ids django__django-11583 \
    --predictions_path gold \
    --output_dir ./traces_test_fixed \
    --skip-patch \
    --verbose

# Test 4: Validate output
echo ""
echo "Test 4: Validating trace output..."
TRACE_FILE="./traces_test_fixed/django__django-11583/auto_debug.json"

if [ ! -f "$TRACE_FILE" ]; then
    echo "✗ FAIL: Trace file not found: $TRACE_FILE"
    exit 1
fi

# Check if trace file has content
TRACE_COUNT=$(python3 -c "import json; traces = json.load(open('$TRACE_FILE')); print(len(traces))")

if [ "$TRACE_COUNT" -eq "0" ]; then
    echo "✗ FAIL: Trace file is empty"
    cat "$TRACE_FILE"
    exit 1
elif [ "$TRACE_COUNT" -lt "2" ]; then
    echo "⚠ WARNING: Expected at least 2 traces, got $TRACE_COUNT"
    echo "Trace content:"
    cat "$TRACE_FILE"
else
    echo "✓ SUCCESS: Captured $TRACE_COUNT test failure traces"
    echo ""
    echo "Sample trace:"
    python3 -c "
import json
traces = json.load(open('$TRACE_FILE'))
if traces:
    trace = traces[0]
    print(f\"  Node: {trace['nodeid']}\")
    print(f\"  Exception: {trace['exc_type']}: {trace['message']}\")
    print(f\"  Frames: {len(trace['frames'])}\")
    if trace['frames']:
        frame = trace['frames'][0]
        print(f\"  First frame: {frame['file']}:{frame['line']} in {frame['func']}\")
"
fi

echo ""
echo "========================================================================"
echo "All tests completed!"
echo "========================================================================"
