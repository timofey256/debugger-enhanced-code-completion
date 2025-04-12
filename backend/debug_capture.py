import sys
import runpy
import types
import traceback
import os

class Debugger:
    def __init__(self, target_func):
        self.target_func = target_func
        self.trace_log = []
        self.current_trace = []
        self.exception = None

    def trace_func(self, frame, event, arg):
        if event != "line":
            return self.trace_func

        code = frame.f_code
        func_name = code.co_name
        if func_name != self.target_func:
            return self.trace_func

        line_no = frame.f_lineno
        locals_copy = frame.f_locals.copy()

        self.current_trace.append({
            "line": line_no,
            "locals": {k: repr(v) for k, v in locals_copy.items()}
        })

        return self.trace_func

    def run_and_capture(self, test_path: str, func_path: str):
        saved_sys_path = sys.path.copy()
        sys.path.insert(0, os.path.dirname(func_path))

        test_globals = {}
        results = []

        with open(test_path) as f:
            test_code = f.read()

        test_module = compile(test_code, test_path, 'exec')

        # Patch function file
        func_module_name = os.path.splitext(os.path.basename(func_path))[0]
        module = runpy.run_path(test_path)

        for test_func_name in [k for k in module if k.startswith("test_")]:
            self.current_trace = []
            self.exception = None
            sys.settrace(self.trace_func)

            # Run the specific test function under the debugger
            try:
                test_func = module[test_func_name]
                test_func_globals = module
                test_func()  # Execute the test function
            except Exception as e:
                self.exception = traceback.format_exc()
            finally:
                sys.settrace(None)

            results.append({
                "test_func": test_func_name,
                "steps": self.current_trace,
                "exception": self.exception,
                "return": None  # You could track the return value here if needed
            })

        sys.path = saved_sys_path
        return results