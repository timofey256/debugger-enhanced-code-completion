import json
import os
import sys
import traceback as _traceback

from _raw_frame import frame_to_raw_dict


_trace_store = []
_current_exec_tracer = None

_MAX_STEP_FRAMES = 200
_MAX_CALL_FRAMES = 4000


class _ExecutionPathTracer:
    def __init__(self):
        self.called_functions = []
        self.executed_frames = []
        self.step_frames = []

    def _saturated(self):
        return len(self.step_frames) >= _MAX_STEP_FRAMES

    def __call__(self, frame, event, arg):
        if self._saturated():
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
            if len(self.step_frames) < _MAX_STEP_FRAMES:
                self.step_frames.append(
                    frame_to_raw_dict(frame, frame.f_lineno)
                )
            return self
        if event == "return":
            if len(self.executed_frames) < _MAX_CALL_FRAMES:
                self.executed_frames.append(
                    frame_to_raw_dict(frame, frame.f_lineno)
                )
        return self


def _frames_from_traceback(exc_tb):
    frames = []
    tb = exc_tb
    while tb is not None:
        frames.append(frame_to_raw_dict(tb.tb_frame, tb.tb_lineno))
        tb = tb.tb_next
    return frames


def _capture_from_live_tb(test, err, exec_path=None, executed_frames=None, step_frames=None):
    exc_type, exc_value, exc_tb = err
    tb_frames = _frames_from_traceback(exc_tb) if exc_tb is not None else []
    _trace_store.append({
        "nodeid": str(test),
        "exc_type": exc_type.__name__,
        "message": str(exc_value),
        "frames": tb_frames or executed_frames or [],
        "exec_path": exec_path or [],
        "step_frames": step_frames or [],
    })


def inject_django_tracer():
    try:
        import unittest

        OriginalTestResult = unittest.TestResult
        original_addError = OriginalTestResult.addError
        original_addFailure = OriginalTestResult.addFailure
        original_addSubTest = OriginalTestResult.addSubTest
        original_startTest = OriginalTestResult.startTest
        original_stopTest = OriginalTestResult.stopTest
        original_stopTestRun = OriginalTestResult.stopTestRun

        def wrapped_startTest(self, test):
            global _current_exec_tracer
            original_startTest(self, test)
            _current_exec_tracer = _ExecutionPathTracer()
            sys.settrace(_current_exec_tracer)

        def wrapped_stopTest(self, test):
            global _current_exec_tracer
            sys.settrace(None)
            _current_exec_tracer = None
            original_stopTest(self, test)

        def wrapped_addError(self, test, err):
            if err and err[2] is not None:
                exec_path = _current_exec_tracer.called_functions if _current_exec_tracer else []
                executed_frames = _current_exec_tracer.executed_frames if _current_exec_tracer else []
                step_frames = _current_exec_tracer.step_frames if _current_exec_tracer else []
                _capture_from_live_tb(test, err, exec_path, executed_frames, step_frames)
            original_addError(self, test, err)

        def wrapped_addFailure(self, test, err):
            if err and err[2] is not None:
                exec_path = _current_exec_tracer.called_functions if _current_exec_tracer else []
                executed_frames = _current_exec_tracer.executed_frames if _current_exec_tracer else []
                step_frames = _current_exec_tracer.step_frames if _current_exec_tracer else []
                _capture_from_live_tb(test, err, exec_path, executed_frames, step_frames)
            original_addFailure(self, test, err)

        def wrapped_addSubTest(self, test, subtest, err):
            if err is not None and err[2] is not None:
                exec_path = _current_exec_tracer.called_functions if _current_exec_tracer else []
                executed_frames = _current_exec_tracer.executed_frames if _current_exec_tracer else []
                step_frames = _current_exec_tracer.step_frames if _current_exec_tracer else []
                _capture_from_live_tb(subtest, err, exec_path, executed_frames, step_frames)
            original_addSubTest(self, test, subtest, err)

        def wrapped_stopTestRun(self):
            original_stopTestRun(self)
            output_path = os.getenv("AUTO_DEBUG_JSON", "auto_debug.json")
            try:
                with open(output_path, "w") as f:
                    json.dump(_trace_store, f, indent=2)
                if _trace_store:
                    print(
                        f"\n▶ Debug info written to {output_path} ({len(_trace_store)} test failures)",
                        file=sys.stderr,
                    )
            except Exception as e:
                print(f"\n✖ Failed to write debug info: {e}", file=sys.stderr)

        OriginalTestResult.addError = wrapped_addError
        OriginalTestResult.addFailure = wrapped_addFailure
        OriginalTestResult.addSubTest = wrapped_addSubTest
        OriginalTestResult.startTest = wrapped_startTest
        OriginalTestResult.stopTest = wrapped_stopTest
        OriginalTestResult.stopTestRun = wrapped_stopTestRun

        print(
            "DEBUG: unittest.TestResult.{addError,addFailure,addSubTest,startTest,stopTest,stopTestRun} monkey-patched for raw trace collection",
            file=sys.stderr,
        )

    except Exception as e:
        print(f"ERROR: Failed to inject Django tracer: {e}", file=sys.stderr)
        _traceback.print_exc(file=sys.stderr)
