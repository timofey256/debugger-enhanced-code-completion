import json
import pathlib
import sys
import sysconfig
import threading

import pytest

CUTOFF_OFFSET = 1000

_tracing = threading.local()

# Get stdlib paths once at import time
_STDLIB_PATHS = [
    sysconfig.get_path("stdlib"),
    sysconfig.get_path("platstdlib"),
    sys.prefix,
    sys.base_prefix,
]
# Filter out None values and normalize
_STDLIB_PATHS = [p for p in _STDLIB_PATHS if p]


def pytest_addoption(parser):
    parser.addoption(
        "--auto-debug-json",
        action="store",
        default="auto_debug.json",
        help="Path for the JSON dump with test debug data",
    )


def should_trace_file(filename):
    # Skip special files
    skip_substrings = ["<", "frozen", "site-packages", "conftest.py", "pytest", "_pytest", "jsonpickle"]
    if any(s in filename for s in skip_substrings):
        return False
    
    # Skip stdlib
    for stdlib_path in _STDLIB_PATHS:
        if filename.startswith(stdlib_path):
            return False
    
    return True


def safe_repr(v):
    """Use repr() instead of jsonpickle — much faster."""
    try:
        r = repr(v)
        return r[:CUTOFF_OFFSET] if len(r) > CUTOFF_OFFSET else r
    except Exception as e:
        return f"<error: {e}>"


def make_tracer(call_log):
    def tracer(frame, event, arg):
        # Prevent reentrancy
        if getattr(_tracing, 'active', False):
            return None
        
        filename = frame.f_code.co_filename
        
        # Return None to NOT trace into unwanted files
        if not should_trace_file(filename):
            return None
        
        _tracing.active = True
        try:
            if event == "call":
                call_log.append({
                    "event": "call",
                    "file": filename,
                    "line": frame.f_lineno,
                    "func": frame.f_code.co_name,
                    "locals": {k: safe_repr(v) for k, v in frame.f_locals.items()},
                })
                return tracer  # Trace inside this function
            
            elif event == "return":
                call_log.append({
                    "event": "return",
                    "file": filename,
                    "line": frame.f_lineno,
                    "func": frame.f_code.co_name,
                    "return_value": safe_repr(arg),
                })
            
            elif event == "exception":
                exc_type, exc_value, _ = arg
                call_log.append({
                    "event": "exception",
                    "file": filename,
                    "line": frame.f_lineno,
                    "func": frame.f_code.co_name,
                    "exc_type": exc_type.__name__ if exc_type else None,
                    "exc_message": str(exc_value)[:CUTOFF_OFFSET] if exc_value else None,
                })
        finally:
            _tracing.active = False
        
        return None
    
    return tracer


def pytest_configure(config):
    config._auto_debug_store = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    call_log = []
    
    old_trace = sys.gettrace()
    sys.settrace(make_tracer(call_log))
    
    try:
        outcome = yield
    finally:
        sys.settrace(old_trace)
    
    exc_info = None
    excinfo = outcome.excinfo
    if excinfo is not None:
        exc_type, exc_value, _ = excinfo
        exc_info = {
            "exc_type": exc_type.__name__ if exc_type else None,
            "message": str(exc_value)[:CUTOFF_OFFSET] if exc_value else None,
        }
    
    item.config._auto_debug_store.append({
        "nodeid": item.nodeid,
        "passed": outcome.excinfo is None,
        "exception": exc_info,
        "call_trace": call_log,
    })


def pytest_sessionfinish(session, exitstatus):
    path = pathlib.Path(session.config.getoption("--auto-debug-json"))
    path.write_text(json.dumps(session.config._auto_debug_store, indent=2))
    
    tr = session.config.pluginmanager.get_plugin("terminalreporter")
    if tr:
        total = sum(len(t["call_trace"]) for t in session.config._auto_debug_store)
        tr.write_line(f"▶ Debug info written to {path} ({total} events)", bold=True)

