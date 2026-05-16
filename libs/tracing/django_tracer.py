import json
import os
import sys
import traceback as _traceback

from _raw_frame import frame_to_raw_dict


_trace_store = []
_current_exec_tracer = None


class _ExecutionPathTracer:
    def __init__(self):
        self.called_functions = []
        self.executed_frames = []
        self.step_frames = []

    def __call__(self, frame, event, arg):
        if event == "call":
            self.called_functions.append({
                "file": frame.f_code.co_filename,
                "func": frame.f_code.co_name,
                "line": frame.f_lineno,
            })
            return self
        if event == "line":
            self.step_frames.append(
                frame_to_raw_dict(frame, frame.f_lineno)
            )
            return self
        if event == "return":
            self.executed_frames.append(
                frame_to_raw_dict(frame, frame.f_lineno)
            )
        return self


def _capture_from_live_tb(test, err, exec_path=None, executed_frames=None, step_frames=None):
    exc_type, exc_value, _ = err
    _trace_store.append({
        "nodeid": str(test),
        "exc_type": exc_type.__name__,
        "message": str(exc_value),
        "frames": executed_frames or [],
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
