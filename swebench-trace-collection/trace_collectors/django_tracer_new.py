"""
Django/unittest test tracer - monkey-patches unittest.TestResult to capture
live stack traces with local variables.

Mirrors the approach in pytest_tracer.py: intercepts the live
(exc_type, exc_value, exc_tb) tuple in addError/addFailure before
unittest formats it to a string, then walks the traceback chain to
capture frame locals.
"""

import json
import os
import sys
import sysconfig

# Cutoff for variable serialization to prevent huge objects
CUTOFF_OFFSET = 1000

HAS_JSONPICKLE = False
try:
    import jsonpickle
    HAS_JSONPICKLE = True
except ImportError:
    pass

# Global trace store (needed because we're patching methods, not subclassing)
_trace_store = []

# Precompute stdlib paths for filtering
_STDLIB_PATHS = []
for _key in ("stdlib", "platstdlib"):
    _p = sysconfig.get_path(_key)
    if _p:
        _STDLIB_PATHS.append(_p)


def _do_append_frame(frame):
    """
    Filter frames to include only application code.

    Excludes special files, frozen modules, site-packages, and stdlib.
    """
    filename = str(frame.f_code.co_filename)
    skip_substrings = ["<", "frozen", "site-packages"]
    if any(s in filename for s in skip_substrings):
        return False
    if any(filename.startswith(p) for p in _STDLIB_PATHS):
        return False
    return True


def _serialize_locals(frame_locals):
    """Serialize frame locals, handling unserializable objects gracefully."""
    result = {}
    for k, v in frame_locals.items():
        try:
            if HAS_JSONPICKLE:
                result[k] = str(jsonpickle.dumps(v, unpicklable=False))[:CUTOFF_OFFSET]
            else:
                result[k] = repr(v)[:CUTOFF_OFFSET]
        except Exception:
            result[k] = "<unserializable>"
    return result


def _capture_from_live_tb(test, err):
    """
    Walk a live traceback to capture frames with locals.

    Args:
        test: unittest test case instance
        err: (exc_type, exc_value, exc_tb) tuple from addError/addFailure
    """
    exc_type, exc_value, exc_tb = err

    frames = []
    tb = exc_tb
    while tb:
        frame = tb.tb_frame
        if _do_append_frame(frame):
            frames.append({
                "file": frame.f_code.co_filename,
                "line": tb.tb_lineno,
                "func": frame.f_code.co_name,
                "locals": _serialize_locals(frame.f_locals),
            })
        tb = tb.tb_next

    _trace_store.append({
        "nodeid": str(test),
        "exc_type": exc_type.__name__,
        "message": str(exc_value),
        "frames": frames,
    })


def inject_django_tracer():
    """
    Monkey-patch unittest.TestResult to capture live tracebacks with locals.

    Patches addError, addFailure (to capture live traceback objects) and
    stopTestRun (to write the JSON output file).
    """
    try:
        import unittest

        OriginalTestResult = unittest.TestResult
        original_addError = OriginalTestResult.addError
        original_addFailure = OriginalTestResult.addFailure
        original_addSubTest = OriginalTestResult.addSubTest
        original_stopTestRun = OriginalTestResult.stopTestRun

        def wrapped_addError(self, test, err):
            """Capture live traceback before unittest formats it to a string."""
            if err and err[2] is not None:
                _capture_from_live_tb(test, err)
            original_addError(self, test, err)

        def wrapped_addFailure(self, test, err):
            """Capture live traceback before unittest formats it to a string."""
            if err and err[2] is not None:
                _capture_from_live_tb(test, err)
            original_addFailure(self, test, err)

        def wrapped_addSubTest(self, test, subtest, err):
            """Capture live traceback from failing subtests."""
            if err is not None and err[2] is not None:
                _capture_from_live_tb(subtest, err)
            original_addSubTest(self, test, subtest, err)

        def wrapped_stopTestRun(self):
            """Write collected traces to JSON file at end of test run."""
            original_stopTestRun(self)

            output_path = os.getenv("AUTO_DEBUG_JSON", "auto_debug.json")
            try:
                with open(output_path, 'w') as f:
                    json.dump(_trace_store, f, indent=2)
                if _trace_store:
                    print(f"\n▶ Debug info written to {output_path} ({len(_trace_store)} test failures)", file=sys.stderr)
            except Exception as e:
                print(f"\n✖ Failed to write debug info: {e}", file=sys.stderr)

        OriginalTestResult.addError = wrapped_addError
        OriginalTestResult.addFailure = wrapped_addFailure
        OriginalTestResult.addSubTest = wrapped_addSubTest
        OriginalTestResult.stopTestRun = wrapped_stopTestRun

        print("DEBUG: unittest.TestResult.{addError,addFailure,addSubTest,stopTestRun} monkey-patched for trace collection", file=sys.stderr)

    except Exception as e:
        print(f"ERROR: Failed to inject Django tracer: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
