import json
import os
import sys
import traceback as _traceback

from _raw_frame import frame_to_raw_dict


_trace_store = []
_current_exec_tracer = None
_current_test = None

_MAX_STEP_FRAMES = 200
_MAX_CALL_FRAMES = 4000


class _ExecutionPathTracer:
    def __init__(self):
        self.called_functions = []
        self.executed_frames = []
        self.step_frames = []

    def __call__(self, frame, event, arg):
        if len(self.step_frames) >= _MAX_STEP_FRAMES:
            sys.settrace(None)
            return None
        if event == "call":
            if len(self.called_functions) < _MAX_CALL_FRAMES:
                self.called_functions.append({
                    "file": frame.f_code.co_filename,
                    "func": frame.f_code.co_name,
                    "line": frame.f_lineno,
                })
            return self
        if event == "line":
            self.step_frames.append(frame_to_raw_dict(frame, frame.f_lineno))
            return self
        if event == "return":
            if len(self.executed_frames) < _MAX_CALL_FRAMES:
                self.executed_frames.append(frame_to_raw_dict(frame, frame.f_lineno))
        return self


def _frames_from_traceback(exc_tb):
    frames = []
    tb = exc_tb
    while tb is not None:
        frames.append(frame_to_raw_dict(tb.tb_frame, tb.tb_lineno))
        tb = tb.tb_next
    return frames


def _test_id(f):
    try:
        name = getattr(f, "__name__", None) or str(f)
        module = getattr(f, "__module__", None)
        code = getattr(f, "__code__", None)
        path = getattr(code, "co_filename", None)
        if module:
            return "%s::%s" % (module, name)
        if path:
            return "%s::%s" % (path, name)
        return name
    except Exception:
        return str(f)


def _capture(exc_info):
    exc_type, exc_value, exc_tb = exc_info
    tb_frames = _frames_from_traceback(exc_tb) if exc_tb is not None else []
    t = _current_exec_tracer
    _trace_store.append({
        "nodeid": _current_test or "<unknown sympy test>",
        "exc_type": getattr(exc_type, "__name__", str(exc_type)),
        "message": str(exc_value),
        "frames": tb_frames or (t.executed_frames if t else []),
        "exec_path": t.called_functions if t else [],
        "step_frames": t.step_frames if t else [],
    })


def inject_sympy_tracer():
    try:
        try:
            from sympy.utilities.runtests import PyTestReporter
        except Exception:
            from sympy.testing.runtests import PyTestReporter

        original_entering_test = PyTestReporter.entering_test
        original_test_fail = PyTestReporter.test_fail
        original_test_exception = PyTestReporter.test_exception
        original_test_pass = PyTestReporter.test_pass
        original_finish = PyTestReporter.finish

        def wrapped_entering_test(self, f):
            global _current_exec_tracer, _current_test
            _current_test = _test_id(f)
            _current_exec_tracer = _ExecutionPathTracer()
            sys.settrace(_current_exec_tracer)
            return original_entering_test(self, f)

        def wrapped_test_fail(self, exc_info):
            sys.settrace(None)
            _capture(exc_info)
            return original_test_fail(self, exc_info)

        def wrapped_test_exception(self, exc_info):
            sys.settrace(None)
            _capture(exc_info)
            return original_test_exception(self, exc_info)

        def wrapped_test_pass(self, char="."):
            sys.settrace(None)
            return original_test_pass(self, char)

        def wrapped_finish(self):
            global _current_exec_tracer
            sys.settrace(None)
            _current_exec_tracer = None
            output_path = os.getenv("AUTO_DEBUG_JSON", "auto_debug.json")
            try:
                with open(output_path, "w") as fh:
                    json.dump(_trace_store, fh, indent=2)
                if _trace_store:
                    print(
                        "\n▶ Debug info written to %s (%d test failures)"
                        % (output_path, len(_trace_store)),
                        file=sys.stderr,
                    )
            except Exception as exc:
                print("✖ Failed to write debug info: %s" % exc, file=sys.stderr)
            return original_finish(self)

        PyTestReporter.entering_test = wrapped_entering_test
        PyTestReporter.test_fail = wrapped_test_fail
        PyTestReporter.test_exception = wrapped_test_exception
        PyTestReporter.test_pass = wrapped_test_pass
        PyTestReporter.finish = wrapped_finish

        print(
            "DEBUG: sympy PyTestReporter hooked for raw trace collection",
            file=sys.stderr,
        )
    except Exception as exc:
        print("ERROR: Failed to inject sympy tracer: %s" % exc, file=sys.stderr)
        _traceback.print_exc(file=sys.stderr)
