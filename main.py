import unittest
import sys

import inspect
import traceback

import collections
import builtins

# Used to expand memory-objects
def safe_serialize(obj, _visited_ids=None, _depth=0, _max_depth=3):
    try:
        if _visited_ids is None:
            _visited_ids = set()
        obj_id = id(obj)
        if obj_id in _visited_ids:
            return "<circular reference>"
        _visited_ids.add(obj_id)

        if _depth > _max_depth:
            return "<max depth reached>"

        if isinstance(obj, dict):
            return {
                safe_serialize(k, _visited_ids, _depth + 1, _max_depth): safe_serialize(v, _visited_ids, _depth + 1, _max_depth)
                for k, v in obj.items()
            }

        if isinstance(obj, (list, tuple, set)):
            cls = type(obj)
            return cls(safe_serialize(v, _visited_ids, _depth + 1, _max_depth) for v in obj)

        if isinstance(obj, collections.defaultdict):
            return {
                '__default_factory__': repr(obj.default_factory),
                'contents': {
                    safe_serialize(k, _visited_ids, _depth + 1, _max_depth): safe_serialize(v, _visited_ids, _depth + 1, _max_depth)
                    for k, v in obj.items()
                }
            }

        try:
            return repr(obj)
        except Exception:
            return "<unrepr-able>"
    except Exception:
        return obj

def debug_test_case(test_case):
    trace_log = []
    import os
    PROJECT_ROOT = os.path.abspath(os.getcwd())

    def trace_function(frame, event, arg):
        if event not in ("call", "line", "return", "exception"):
            return trace_function

        code = frame.f_code
        func_name = code.co_name
        file_name = code.co_filename
        line_no = frame.f_lineno

        # Skip frames outside project directory
        if not os.path.abspath(file_name).startswith(PROJECT_ROOT) or "site-packages" in file_name or "frozen" in file_name:
            return

        # Extract source line
        try:
            source_line = inspect.getsourcefile(code)
            source_line = inspect.getsourcelines(code)[0][line_no - code.co_firstlineno].strip()
        except Exception:
            source_line = ""

        # Capture local variables
        local_vars = {
            k: safe_serialize(v)
            for k, v in frame.f_locals.items()
        }

        trace_log.append({
            'event': event,
            'func_name': func_name,
            'file_name': file_name,
            'line_no': line_no,
            'source': source_line,
            'locals': local_vars,
            'arg': safe_repr(arg) if event == 'return' else None
        })

        return trace_function

    def safe_repr(obj):
        try:
            return repr(obj)
        except Exception:
            return '<unrepr-able>'

    sys.settrace(trace_function)
    try:
        test_case()
    except Exception as e:
        trace_log.append({
            'event': 'exception',
            'exception': traceback.format_exc()
        })
    finally:
        sys.settrace(None)

    return trace_log

class DebuggingTestRunner(unittest.TextTestRunner):
    def run(self, test):
        result = super().run(test)
        return result

def process_trace_log(trace_log):
    processed = []

    for i, record in enumerate(trace_log):
        block = ""
        if record["event"] == "call":
            block += f"Entering function {record["func_name"]} at line {record["line_no"]} in file {record["file_name"]}\n"
        elif record["event"] == "line":
            block += f"Processing line in function {record["func_name"]} at line {record["line_no"]} in file {record["file_name"]}\n"
        elif record["event"] == "return":
            block += f"Returning from {record["func_name"]} at line {record["line_no"]} in file {record["file_name"]}\n"
            block += f"Returning value of this line is: {record["arg"]}\n"
        elif record["event"] == "exception":
            block += f"Exception: {record}\n"
        else:
            print(record["event"])
            raise f"Unknown event: {record["event"]}" 

        if "source" in record.keys():
            block += f"Source code at this line: {record["source"]}\n"
        if "locals" in record.keys():
            block += f"Local before this line: {record["locals"]}\n"
        if i != len(trace_log)-1 and "locals" in trace_log[i+1].keys():
            block += f"Local after this line: {trace_log[i+1]["locals"]}\n"

        processed.append(block)

    return processed

def debug_line_by_line_in_test_file(test_file_path, test_method=None, save_json=True):
    with open(test_file_path, 'r') as f:
        lines = f.readlines()

    test_module = {"__file__": test_file_path, "__name__": "__main__"}
    exec("".join(lines), test_module)

    if test_method is not None:
        test_prefix = test_method
    else:
        test_prefix = "test_"

    test_methods = [func for func in test_module if func.startswith(test_prefix)]

    trace_log = []
    for test_method in test_methods:
        print(f"Debugging test: {test_method}")
        test_case = test_module[test_method]
        trace_log = debug_test_case(test_case)

    # Save trace log to JSON file for later processing
    if save_json:
        import json
        import os
        import time
        
        timestamp = int(time.time())
        output_dir = "experiment_runs"
        os.makedirs(output_dir, exist_ok=True)
        
        # Create filename based on test method
        if test_method is not None:
            json_filename = f"{output_dir}/trace_{os.path.basename(test_file_path)}_{test_method}_{timestamp}.json"
        else:
            json_filename = f"{output_dir}/trace_{os.path.basename(test_file_path)}_{timestamp}.json"
        
        with open(json_filename, 'w') as f:
            try:
                json.dump(trace_log, f, indent=2)
            except Exception as e:
                print(f"WARNING: failed to save the element: {e}. Element: {trace_log}")
        
        print(f"Trace log saved to {json_filename}")

    result = process_trace_log(trace_log)
    for b in result:
        print(b)
        print()
    
    return trace_log, json_filename if save_json else None

if __name__ == "__main__":
    tests_functions_path = sys.argv[1]
    test_function_name = None
    if len(sys.argv) > 2:
        test_function_name = sys.argv[2]

    debug_line_by_line_in_test_file(tests_functions_path, test_function_name)