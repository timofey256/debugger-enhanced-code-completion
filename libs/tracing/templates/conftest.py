"""
Copied to /testbed/conftest.py inside the eval container by
libs/tracing/templates/pytest_conftest_setup.sh. Imports the shared
raw-frame helper from /opt/tracers/_raw_frame.py (on PYTHONPATH).
"""

import json
import os
import pathlib
import sys

import pytest

from _raw_frame import frame_to_raw_dict, serialize_locals_raw  # noqa: E402


def pytest_addoption(parser):
    parser.addoption(
        "--auto-debug-json",
        action="store",
        default="auto_debug.json",
        help="Path for the JSON dump with failing-test debug data",
    )


class _ExecutionPathTracer:
    def __init__(self):
        self.called_functions = []

    def __call__(self, frame, event, arg):
        if event == "call":
            self.called_functions.append({
                "file": frame.f_code.co_filename,
                "func": frame.f_code.co_name,
                "line": frame.f_lineno,
            })
        return None


def pytest_configure(config):
    config._auto_debug_store = []


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_call(item):
    tracer = _ExecutionPathTracer()
    old_trace = sys.gettrace()
    sys.settrace(tracer)
    try:
        yield
    finally:
        sys.settrace(old_trace)
    item._exec_path = tracer.called_functions


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()

    if rep.when != "call" or rep.passed:
        return

    excinfo = call.excinfo
    frames = []
    tb = excinfo.tb
    while tb:
        frames.append(frame_to_raw_dict(tb.tb_frame, tb.tb_lineno))
        tb = tb.tb_next

    item.config._auto_debug_store.append({
        "nodeid": item.nodeid,
        "exc_type": excinfo.type.__name__,
        "message": str(excinfo.value),
        "frames": frames,
        "exec_path": getattr(item, "_exec_path", []),
    })


def pytest_sessionfinish(session, exitstatus):
    output = os.environ.get("AUTO_DEBUG_JSON") or session.config.getoption("--auto-debug-json")
    path = pathlib.Path(output)
    path.write_text(json.dumps(session.config._auto_debug_store, indent=2))
    tr = session.config.pluginmanager.get_plugin("terminalreporter")
    if tr:
        tr.write_line(f"▶ Debug info written to {path}", bold=True)
