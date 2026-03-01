# SWE-bench Trace Collection

Collect stack traces from test failures in the SWE-bench dataset across multiple testing frameworks (pytest, unittest, Django).

## Overview

This project extends the existing pytest-based trace collection system to work with the SWE-bench benchmark dataset. It collects detailed stack traces, local variables, and exception information from failing tests to enable better debugging and code completion.

## Features

- **Multi-framework support**: pytest, unittest, Django test runner
- **Failures-only mode**: Lightweight trace collection focused on test failures
- **Docker integration**: Works with SWE-bench's containerized test environment
- **Automatic framework detection**: Identifies test framework per repository
- **Unified output format**: Consistent JSON structure across all frameworks

## Architecture

```
┌──────────────────────────────────────────────┐
│ Layer 1: Framework Detection & Injection    │
└──────────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────┐
│ Layer 2: Trace Collection (Framework)       │
└──────────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────┐
│ Layer 3: Aggregation & Storage              │
└──────────────────────────────────────────────┘
```

## Installation

```bash
# Install dependencies
pip install jsonpickle datasets

# Set up the project
cd swebench-trace-collection
```

## Usage

### Collect traces from SWE-bench Lite

```bash
python scripts/collect_swebench_traces.py \
    --dataset princeton-nlp/SWE-bench_Lite \
    --output-dir ./swebench_traces \
    --max-workers 8
```

### Validate collected traces

```bash
python scripts/validate_traces.py ./swebench_traces
```

### Generate coverage report

```bash
python scripts/generate_report.py ./swebench_traces
```

## Output Format

Traces are collected in JSON format:

```json
{
  "nodeid": "test_module.py::TestClass::test_method",
  "exc_type": "AssertionError",
  "message": "Expected value did not match",
  "frames": [
    {
      "file": "/path/to/file.py",
      "line": 42,
      "func": "function_name",
      "locals": {
        "var1": "value1",
        "var2": "value2"
      }
    }
  ]
}
```

## Project Structure

```
swebench-trace-collection/
├── trace_collectors/       # Framework-specific trace collectors
├── swebench_integration/   # SWE-bench integration layer
├── scripts/                # CLI scripts for collection and validation
├── tests/                  # Unit and integration tests
├── config/                 # Configuration and cache files
└── README.md
```

## Development

### Running tests

```bash
pytest tests/
```

### Target datasets

- **SWE-bench Lite**: 534 instances (for validation)
- **Full SWE-bench**: 2,294 instances (production run)

## Success Criteria

- **Pytest repos**: 95%+ success rate
- **Unittest repos**: 90%+ success rate
- **Overall**: 90%+ success rate on SWE-bench Lite

## License

MIT
