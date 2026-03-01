# SWE-bench Trace Collection - Usage Guide

## Overview

This guide explains how to collect detailed stack traces from failing tests in the SWE-bench dataset.

## Prerequisites

1. **Docker**: Ensure Docker is installed and running
2. **Python**: Python 3.8+ with required dependencies
3. **SWE-bench**: The SWE-bench repository should be accessible

## Installation

```bash
cd swebench-trace-collection
pip install -r requirements.txt
```

Required dependencies:
- `jsonpickle>=3.0.0` - For serializing variables
- `datasets>=2.0.0` - For loading SWE-bench dataset
- `pytest>=7.0.0` - For testing
- `docker` - Python Docker SDK

## Quick Start

### 1. Collect Traces from a Single Instance

```bash
python scripts/run_swebench_with_traces.py \
    --dataset princeton-nlp/SWE-bench_Lite \
    --instance_ids django__django-11583 \
    --predictions_path gold \
    --output_dir ./traces
```

**Output:**
- Trace file: `./traces/django__django-11583/auto_debug.json`
- Test output: `./traces/django__django-11583/test_output.txt`
- Patch applied: `./traces/django__django-11583/patch.diff`

### 2. Collect Traces from Multiple Instances

```bash
python scripts/run_swebench_with_traces.py \
    --dataset princeton-nlp/SWE-bench_Lite \
    --instance_ids django__django-11583 flask__flask-4992 sympy__sympy-18532 \
    --predictions_path gold \
    --output_dir ./traces
```

### 3. Collect Traces from All Instances (Sequential)

```bash
python scripts/run_swebench_with_traces.py \
    --dataset princeton-nlp/SWE-bench_Lite \
    --predictions_path gold \
    --output_dir ./traces_lite
```

## Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--dataset` | SWE-bench dataset name | `princeton-nlp/SWE-bench_Lite` |
| `--split` | Dataset split | `test` |
| `--instance_ids` | Specific instances to run (space-separated) | All instances |
| `--predictions_path` | Path to predictions file or 'gold' | `gold` |
| `--output_dir` | Output directory for traces | `./traces` |
| `--timeout` | Timeout for test execution (seconds) | None |
| `--force_rebuild` | Force rebuild of Docker images | False |
| `--nocache` | Don't use cache when building images | False |
| `--run_id` | Run ID for this execution | `trace_collection` |
| `--verbose` | Enable verbose logging | False |

## Output Format

Each instance produces a trace file: `{output_dir}/{instance_id}/auto_debug.json`

**Trace File Structure:**
```json
[
  {
    "nodeid": "tests/test_module.py::TestClass::test_method",
    "exc_type": "AssertionError",
    "message": "assert 42 == 100",
    "frames": [
      {
        "file": "/testbed/module.py",
        "line": 42,
        "func": "function_name",
        "locals": {
          "variable1": "value1",
          "variable2": "value2"
        }
      }
    ]
  }
]
```

**Additional Files:**
- `test_output.txt` - Complete test execution output
- `patch.diff` - Patch that was applied
- `eval.sh` - Evaluation script that was run

## Framework Support

The trace collector automatically detects and supports:

1. **pytest** - Uses conftest.py injection
2. **unittest** - Uses TestResult monkey-patching
3. **Django** - Uses TestResult with Django-specific handling

Detection is based on the test command in the SWE-bench instance.

## Validation

Validate collected traces:

```bash
python scripts/validate_traces.py ./traces --verbose
```

This checks:
- Valid JSON format
- Required fields present
- Non-empty stack frames
- Serializable local variables

## Troubleshooting

### No Trace File Created

**Possible causes:**
1. Tests passed (no failures to trace)
2. Trace collection didn't activate
3. Framework detection failed

**Debug steps:**
```bash
# Check test output
cat ./traces/{instance_id}/test_output.txt

# Verify Docker setup
docker ps -a | grep sweb.eval

# Run with verbose logging
python scripts/run_swebench_with_traces.py --verbose ...
```

### Trace File Empty

The trace file will be an empty list `[]` if:
- All tests passed
- Tests failed but trace collector didn't capture them

### Docker Permission Errors

If you see permission errors with `/trace_output`:

```bash
# Ensure output directory is writable
chmod -R 777 ./traces
```

### Container Cleanup

If containers aren't being cleaned up:

```bash
# Manual cleanup
docker ps -a | grep sweb.eval | awk '{print $1}' | xargs docker rm -f
```

## Example Workflow

### Complete Example: Trace Collection Pipeline

```bash
# 1. Set up environment
cd swebench-trace-collection
pip install -r requirements.txt

# 2. Test with a single instance
python scripts/run_swebench_with_traces.py \
    --instance_ids django__django-11583 \
    --predictions_path gold \
    --output_dir ./test_traces \
    --verbose

# 3. Validate the output
python scripts/validate_traces.py ./test_traces --verbose

# 4. Inspect the trace
cat ./test_traces/django__django-11583/auto_debug.json | python -m json.tool

# 5. Run on a small batch
python scripts/run_swebench_with_traces.py \
    --instance_ids django__django-11583 flask__flask-4992 sympy__sympy-18532 \
    --predictions_path gold \
    --output_dir ./batch_traces

# 6. Check summary
cat ./batch_traces/summary_trace_collection.json | python -m json.tool
```

## Advanced Usage

### Custom Predictions

Create a predictions file (`predictions.jsonl`):
```json
{"instance_id": "django__django-11583", "model_name_or_path": "my-model", "model_patch": "diff content..."}
{"instance_id": "flask__flask-4992", "model_name_or_path": "my-model", "model_patch": "diff content..."}
```

Run with custom predictions:
```bash
python scripts/run_swebench_with_traces.py \
    --predictions_path predictions.jsonl \
    --output_dir ./custom_traces
```

### Timeout Configuration

Set a timeout for long-running tests:

```bash
python scripts/run_swebench_with_traces.py \
    --instance_ids slow_instance \
    --timeout 600 \  # 10 minutes
    --output_dir ./traces
```

### Debugging Specific Instances

To debug why an instance isn't producing traces:

```bash
# 1. Run with verbose logging
python scripts/run_swebench_with_traces.py \
    --instance_ids problematic_instance \
    --verbose \
    --output_dir ./debug_traces

# 2. Check the container logs
# (Container ID will be in the verbose output)
docker logs <container_id>

# 3. Inspect the container
docker run -it <image_name> /bin/bash
# Then manually run: /bin/bash /eval.sh
```

## Performance Considerations

- **Sequential Processing**: Current implementation processes instances one at a time
- **Docker Images**: Images are cached after first build
- **Disk Space**: Each instance may require 1-5 GB depending on dependencies
- **Time**: Expect 2-10 minutes per instance depending on test suite size

## Success Criteria

Trace collection is successful when:
- ✅ `auto_debug.json` file exists
- ✅ File contains valid JSON (list of trace objects)
- ✅ Each trace has `nodeid`, `exc_type`, `message`, and `frames`
- ✅ Frames contain `file`, `line`, `func`, and `locals`
- ✅ No errors in `test_output.txt` related to trace collection

## Future Enhancements

Potential improvements (not yet implemented):
- Parallel processing with multiple workers
- Integration with SWE-bench's reporting system
- Support for additional test frameworks
- Trace deduplication and analysis tools
- Automatic trace summarization

## Support

For issues or questions:
1. Check `test_output.txt` for test execution logs
2. Run with `--verbose` for detailed logging
3. Inspect Docker containers manually
4. Validate traces with `validate_traces.py`

## Architecture

### Components

1. **container_hooks.py** - Adds trace collection volumes to Docker containers
2. **eval_script_injector.py** - Injects conftest.py setup for pytest
3. **wrapper.py** - Orchestrates trace collection workflow
4. **run_swebench_with_traces.py** - Main CLI entry point

### Workflow

```
1. Load SWE-bench dataset
2. Detect framework (pytest/unittest/django)
3. Create Docker container with trace volumes
4. Inject trace collectors
5. Run tests
6. Collect traces
7. Validate and save output
```

### Integration Points

- **SWE-bench Dataset**: Uses standard Hugging Face datasets library
- **Docker**: Reuses SWE-bench's Docker infrastructure
- **TestSpec**: Compatible with SWE-bench's TestSpec format
- **Trace Collectors**: Independent modules in `/trace_collectors`
