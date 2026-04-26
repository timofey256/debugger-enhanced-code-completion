"""
Pytest trace collector (conftest.py template).

This is the pytest hook implementation for capturing test failures.
Copy this file as conftest.py to the test project root.

Source: pytest-smart-debugger-extension/templates/conftest.py
"""

import json
import pathlib
import sys
import sysconfig
import pytest

# Cutoff for variable serialization to prevent huge objects
CUTOFF_OFFSET = 1000

HAS_JSONPICKLE = False
try:
    import jsonpickle
    HAS_JSONPICKLE = True
except ImportError:
    pass

# Precompute stdlib paths for filtering
_STDLIB_PATHS = []
for _key in ("stdlib", "platstdlib"):
    _p = sysconfig.get_path(_key)
    if _p:
        _STDLIB_PATHS.append(_p)


def pytest_addoption(parser):
    """Add command-line option for output path."""
    parser.addoption(
        "--auto-debug-json",
        action="store",
        default="auto_debug.json",
        help="Path for the JSON dump with failing-test debug data",
    )


def do_append_frame(frame):
    """
    Filter frames to include only application code.

    Excludes special files, frozen modules, site-packages, and stdlib.
    Always includes /testbed/ code even if installed in site-packages.
    """
    filename = str(frame.f_code.co_filename)
    skip_substrings = ["<", "frozen"]
    if any(s in filename for s in skip_substrings):
        return False
    if "site-packages" in filename:
        return False
    if any(filename.startswith(p) for p in _STDLIB_PATHS):
        return False
    return True


def _is_testbed_project_file(filename):
    """Check if a file is project source (under /testbed/ but not site-packages/stdlib)."""
    return '/testbed/' in filename and 'site-packages' not in filename


class _ExecutionPathTracer:
    """Lightweight sys.settrace callback that records testbed function calls.

    Captures which project functions are called during test execution,
    even if they return successfully and don't appear in exception tracebacks.
    This is critical for wrong-return-value bugs where the buggy function
    completes normally but produces an incorrect result.
    """

    MAX_ENTRIES = 500

    def __init__(self):
        self.called_functions = []
        self._seen = set()

    def __call__(self, frame, event, arg):
        if event == 'call' and len(self.called_functions) < self.MAX_ENTRIES:
            filename = frame.f_code.co_filename
            if _is_testbed_project_file(filename):
                key = (filename, frame.f_code.co_name)
                if key not in self._seen:
                    self._seen.add(key)
                    self.called_functions.append({
                        'file': filename,
                        'func': frame.f_code.co_name,
                        'line': frame.f_lineno,
                    })
        return None  # No per-line tracing needed


def pytest_configure(config):
    """Initialize storage for debug information."""
    # Place to accumulate results
    config._auto_debug_store = []


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_call(item):
    """Trace function calls during test execution to capture execution path."""
    tracer = _ExecutionPathTracer()
    old_trace = sys.gettrace()
    sys.settrace(tracer)
    try:
        yield
    finally:
        sys.settrace(old_trace)
    item._exec_path = tracer.called_functions


# Run *before* normal make-report so we keep excinfo
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Capture test failures with detailed stack traces.

    This hook intercepts test execution after each phase (setup, call, teardown)
    and captures exception information for failing tests.
    """
    outcome = yield  # Let pytest run the real hook chain
    rep = outcome.get_result()  # TestReport

    if rep.when != "call" or rep.passed:
        return  # Only care about failing test body

    excinfo = call.excinfo  # pytest.ExceptionInfo – live traceback
    frames = []
    tb = excinfo.tb

    # Walk the traceback chain
    while tb:
        frame = tb.tb_frame

        if do_append_frame(frame):
            frame_locals = {}
            for k, v in frame.f_locals.items():
                try:
                    if HAS_JSONPICKLE:
                        frame_locals[k] = str(jsonpickle.dumps(v, unpicklable=False))[:CUTOFF_OFFSET]
                    else:
                        frame_locals[k] = repr(v)[:CUTOFF_OFFSET]
                except Exception:
                    frame_locals[k] = "<unserializable>"
            frames.append(
                {
                    "file": frame.f_code.co_filename,
                    "line": tb.tb_lineno,
                    "func": frame.f_code.co_name,
                    "locals": frame_locals,
                }
            )

        tb = tb.tb_next

    item.config._auto_debug_store.append(
        {
            "nodeid": item.nodeid,  # Fully-qualified test id
            "exc_type": excinfo.type.__name__,
            "message": str(excinfo.value),
            "frames": frames,
            "exec_path": getattr(item, '_exec_path', []),
        }
    )


def pytest_sessionfinish(session, exitstatus):
    """Write collected debug information to JSON file."""
    import os
    # Prefer AUTO_DEBUG_JSON env var (set by eval script for Docker volume output),
    # fall back to --auto-debug-json CLI option
    output = os.environ.get("AUTO_DEBUG_JSON") or session.config.getoption("--auto-debug-json")
    path = pathlib.Path(output)
    path.write_text(json.dumps(session.config._auto_debug_store, indent=2))
    tr = session.config.pluginmanager.get_plugin("terminalreporter")
    if tr:
        tr.write_line(f"▶ Debug info written to {path}", bold=True)
