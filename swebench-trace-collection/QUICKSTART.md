## Quick Start Guide

### Installation

```bash
cd swebench-trace-collection

# Install dependencies
pip install -r requirements.txt
```

### Testing the Tracers

#### Test Unittest Tracer

```bash
# Run the test runner to verify unittest tracer works
python tests/test_unittest_runner.py
```

Expected output:
```
Running sample tests with DebugTestResult...

Tests run: 3
Failures: 1
Errors: 1
Debug traces captured: 2

Captured traces:
1. test_assertion_failure (tests.sample_failing_tests.SampleTests)
   Exception: AssertionError: 42 != 100
   Frames: N

2. test_exception_error (tests.sample_failing_tests.SampleTests)
   Exception: ZeroDivisionError: division by zero
   Frames: N

✓ Output file created: auto_debug.json
```

#### Test Pytest Tracer

```bash
# Copy conftest to a test project
cp trace_collectors/pytest_tracer.py /path/to/test/project/conftest.py

# Run pytest
cd /path/to/test/project
pytest --auto-debug-json=traces.json
```

### Basic Usage

#### 1. Framework Detection

```python
from swebench_integration.framework_detector import FrameworkDetector

detector = FrameworkDetector()
framework = detector.detect("django__django-12345", test_command="./manage.py test")
print(f"Framework: {framework}")  # Output: django
```

#### 2. Volume Management

```python
from swebench_integration.volume_manager import TraceOutputManager

manager = TraceOutputManager(base_dir="./my_traces")

# Create output directory for instance
output_dir = manager.create_output_volume("instance-123")

# Get Docker mount arguments
mount_args = manager.get_docker_mount_args("instance-123")
print(mount_args)  # ["-v", "/path/to/my_traces/instance-123:/trace_output:rw"]
```

#### 3. Collect Traces

```bash
# Collect from specific instances
python scripts/collect_swebench_traces.py \
    --instances django__django-12345 flask__flask-456 \
    --output-dir ./traces \
    --max-workers 4

# Collect from dataset
python scripts/collect_swebench_traces.py \
    --dataset princeton-nlp/SWE-bench_Lite \
    --output-dir ./traces \
    --max-workers 8
```

#### 4. Validate Traces

```bash
python scripts/validate_traces.py ./traces --verbose
```

#### 5. Generate Report

```bash
python scripts/generate_report.py ./traces
```

### Output Format

All tracers produce the same JSON format:

```json
[
  {
    "nodeid": "test_file.py::TestClass::test_method",
    "exc_type": "AssertionError",
    "message": "assert 42 == 100",
    "frames": [
      {
        "file": "/path/to/file.py",
        "line": 42,
        "func": "test_method",
        "locals": {
          "self": "<TestClass object>",
          "x": "42",
          "expected": "100"
        }
      }
    ]
  }
]
```

### Next Steps

1. **Complete integration tests** - Test with real SWE-bench instances
2. **Enhance framework detection** - Parse SWE-bench constants.py
3. **Add SWE-bench hooks** - Minimal modification to TestSpec
4. **Run pilot** - 50 diverse instances for validation
