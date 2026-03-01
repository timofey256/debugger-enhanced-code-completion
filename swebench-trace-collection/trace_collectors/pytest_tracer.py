"""
Pytest trace collector (conftest.py template).

This is the pytest hook implementation for capturing test failures.
Copy this file as conftest.py to the test project root.

Source: pytest-smart-debugger-extension/templates/conftest.py
"""

import json
import pathlib
import sysconfig
import jsonpickle
import pytest

# Cutoff for variable serialization to prevent huge objects
CUTOFF_OFFSET = 1000

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
    """
    filename = str(frame.f_code.co_filename)
    skip_substrings = ["<", "frozen", "site-packages"]
    if any(s in filename for s in skip_substrings):
        return False
    if any(filename.startswith(p) for p in _STDLIB_PATHS):
        return False
    return True


def pytest_configure(config):
    """Initialize storage for debug information."""
    # Place to accumulate results
    config._auto_debug_store = []


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
            frames.append(
                {
                    "file": frame.f_code.co_filename,
                    "line": tb.tb_lineno,
                    "func": frame.f_code.co_name,
                    # jsonpickle with cutoff prevents recursion / huge blobs
                    "locals": {
                        k: str(jsonpickle.dumps(v, unpicklable=False))[:CUTOFF_OFFSET]
                        for k, v in frame.f_locals.items()
                    },
                }
            )

        tb = tb.tb_next

    item.config._auto_debug_store.append(
        {
            "nodeid": item.nodeid,  # Fully-qualified test id
            "exc_type": excinfo.type.__name__,
            "message": str(excinfo.value),
            "frames": frames,
        }
    )


def pytest_sessionfinish(session, exitstatus):
    """Write collected debug information to JSON file."""
    path = pathlib.Path(session.config.getoption("--auto-debug-json"))
    path.write_text(json.dumps(session.config._auto_debug_store, indent=2))
    tr = session.config.pluginmanager.get_plugin("terminalreporter")
    if tr:
        tr.write_line(f"▶ Debug info written to {path}", bold=True)
