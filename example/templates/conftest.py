import json, pathlib
import pytest

def pytest_addoption(parser):
    parser.addoption(
        "--auto-debug-json",
        action="store",
        default="auto_debug.json",
        help="Path for the JSON dump with failing-test debug data",
    )

def do_append_frame(frame):
    filename = str(frame.f_code.co_filename)
    skip_substrings = ["<", "frozen", "site-packages"]
    skip_substring_in_filename = any([skip_ss in filename for skip_ss in skip_substrings])

    return not skip_substring_in_filename    

def pytest_configure(config):
    # place to accumulate results
    config._auto_debug_store = []

# run *before* normal make-report so we keep excinfo
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield                # let pytest run the real hook chain
    rep = outcome.get_result()     # TestReport

    if rep.when != "call" or rep.passed:
        return                     # only care about failing test body

    excinfo = call.excinfo         # pytest.ExceptionInfo – live traceback
    frames = []
    tb = excinfo.tb
    while tb:
        frame = tb.tb_frame

        if do_append_frame(frame):
            frames.append(
                {
                    "file": frame.f_code.co_filename,
                    "line": tb.tb_lineno,
                    "func": frame.f_code.co_name,
                    # repr() prevents recursion / huge blobs
                    "locals": {k: repr(v) for k, v in frame.f_locals.items()},
                }
            )

        tb = tb.tb_next

    item.config._auto_debug_store.append(
        {
            "nodeid": item.nodeid,                 # fully-qualified test id
            "exc_type": excinfo.type.__name__,
            "message": str(excinfo.value),
            "frames": frames,
        }
    )

def pytest_sessionfinish(session, exitstatus):
    path = pathlib.Path(session.config.getoption("--auto-debug-json"))
    path.write_text(json.dumps(session.config._auto_debug_store, indent=2))
    tr = session.config.pluginmanager.get_plugin("terminalreporter")
    if tr:
        tr.write_line(f"▶ Debug info written to {path}", bold=True)
