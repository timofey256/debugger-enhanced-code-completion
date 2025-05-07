"""Main module for running debug traces."""

import os
import sys
import json
import time
import inspect
import unittest
import traceback
import collections
from typing import Any, Dict, List, Optional, Tuple, Set
from datetime import datetime

def get_class_interface(cls):
    """Get the interface of a class."""
    interface = {}
    for name, member in inspect.getmembers(cls, predicate=inspect.isfunction):
        if not name.startswith('_'):
            try:
                sig = str(inspect.signature(member))
            except ValueError:
                sig = '(...)'
            doc = inspect.getdoc(member) or ''
            interface[name] = {
                'signature': sig,
                'doc': doc
            }
    return interface

def safe_serialize(obj, _visited_ids=None, _depth=0, _max_depth=3):
    """Safely serialize an object to a JSON-compatible format."""
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
    """Debug a test case and collect trace information."""
    trace_log = []
    PROJECT_ROOT = os.path.abspath(os.getcwd())

    def trace_function(frame, event, arg):
        if event not in ("call", "line", "return", "exception"):
            return trace_function

        code = frame.f_code
        func_name = code.co_name
        file_name = code.co_filename
        line_no = frame.f_lineno

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

        record = {
            'event': event,
            'func_name': func_name,
            'file_name': file_name,
            'line_no': line_no,
            'source': source_line,
            'locals': local_vars,
            'arg': safe_repr(arg) if event == 'return' else None
        }
        
        # Store exception information if available
        if event == 'exception' and arg is not None:
            exc_type, exc_value, exc_traceback = arg
            record['exception_type'] = safe_repr(exc_type)
            record['exception_value'] = safe_repr(exc_value)
            record['exception_traceback'] = safe_repr(traceback.format_tb(exc_traceback))

        # Only trace files in our project
        if "site-packages" in file_name or not (file_name.startswith(PROJECT_ROOT) or file_name.startswith(os.path.join(PROJECT_ROOT, "example"))):
            return trace_function

        if event == 'exception':
            instance = frame.f_locals.get('self')
            if instance:
                cls = getattr(instance, '__class__', None)
                if cls:
                    class_doc = inspect.getdoc(cls) or ""
                    methods = inspect.getmembers(cls, predicate=inspect.isfunction)
                    class_context = {}

                    for name, method in methods:
                        if not name.startswith('_') or name == '__init__':
                            try:
                                source_lines, _ = inspect.getsourcelines(method)
                                method_source = ''.join(source_lines).strip()
                            except Exception:
                                method_source = "<source unavailable>"
                            method_doc = inspect.getdoc(method) or ""
                            class_context[name] = {
                                'doc': method_doc,
                                'source': method_source
                            }

                    record['class_context'] = {
                        'class_doc': class_doc,
                        'methods': class_context
                    }

        trace_log.append(record)
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
    """Custom test runner for debugging."""
    def run(self, test):
        result = super().run(test)
        return result

def process_trace_log(trace_log):
    """Process the trace log into a human-readable format."""
    processed = []

    for i, record in enumerate(trace_log):
        block = ""
        if record["event"] == "call":
            if record.get("class_name"):
                block += f"Entering method {record['class_name']}.{record['func_name']} at line {record['line_no']} in file {record['file_name']}\n"
            else:
                block += f"Entering function {record['func_name']} at line {record['line_no']} in file {record['file_name']}\n"
        elif record["event"] == "line":
            block += f"Processing line in function {record['func_name']} at line {record['line_no']} in file {record['file_name']}\n"
        elif record["event"] == "return":
            block += f"Returning from {record['func_name']} at line {record['line_no']} in file {record['file_name']}\n"
            block += f"Returning value of this line is: {record['arg']}\n"
        elif record["event"] == "exception":
            block += f"Exception occured\n"
            if 'line_no' in record: 
                block += f"Exception line number: {record['line_no']}\n"
            if 'file_name' in record: 
                block += f"Exception in file: {record['file_name']}\n"
            if 'func_name' in record: 
                block += f"Exception function: {record['func_name']}\n"
            if "exception_type" in record:
                block += f"Exception type: {record['exception_type']}\n"
            if "exception_value" in record:
                block += f"Exception value: {record['exception_value']}\n"
        else:
            print(record["event"])
            raise Exception(f"Unknown event: {record['event']}")

        if i != len(trace_log) - 1 and "locals" in trace_log[i + 1]:
            block += f"Local after this line: {trace_log[i + 1]['locals']}\n"

        # Include class interface if available
        if record.get("class_interface"):
            block += f"Class interface for {record['class_name']}:\n"
            for method, details in record["class_interface"].items():
                block += f"  {method}{details['signature']}\n"
                if details['doc']:
                    block += f"    Docstring: {details['doc']}\n"

        processed.append(block)

    return processed

def debug_line_by_line_in_test_file(test_file_path, test_method=None, save_json=True):
    """Debug a test file line by line."""
    print(f"Starting debug trace for {test_file_path}")
    
    # Add the src directory to Python path for imports
    test_dir = os.path.dirname(test_file_path)
    if "example/calculator" in test_file_path:
        src_path = os.path.join(os.path.dirname(test_dir), "src")
        print(f"Adding {src_path} to Python path")
        sys.path.insert(0, src_path)
    
    try:
        with open(test_file_path, 'r') as f:
            lines = f.readlines()
        print(f"Successfully read {len(lines)} lines from {test_file_path}")

        test_module = {"__file__": test_file_path, "__name__": "__main__"}
        print("Executing test module...")
        exec("".join(lines), test_module)
        print("Test module executed successfully")

        if test_method is not None:
            test_prefix = test_method
        else:
            test_prefix = "test_"

        test_methods = [func for func in test_module if func.startswith(test_prefix)]
        print(f"Found {len(test_methods)} test methods: {test_methods}")

        trace_log = []
        for test_method in test_methods:
            print(f"Debugging test: {test_method}")
            test_case = test_module[test_method]
            try:
                trace_log = debug_test_case(test_case)
                print(f"Successfully traced {test_method}")
            except Exception as e:
                print(f"Error tracing {test_method}: {str(e)}")
                import traceback
                traceback.print_exc()

        # Save trace log to JSON file for later processing
        if save_json and trace_log:
            timestamp = int(time.time())
            output_dir = "experiment_runs"
            os.makedirs(output_dir, exist_ok=True)
            
            # Create filename based on test method
            if test_method is not None:
                json_filename = f"{output_dir}/trace_{os.path.basename(test_file_path)}_{test_method}_{timestamp}.json"
            else:
                json_filename = f"{output_dir}/trace_{os.path.basename(test_file_path)}_{timestamp}.json"
            
            # Custom JSON encoder to handle sets and other non-serializable types
            class CustomJSONEncoder(json.JSONEncoder):
                def default(self, obj):
                    if isinstance(obj, set):
                        return list(obj)
                    try:
                        return str(obj)
                    except:
                        return "<unserializable>"
            
            with open(json_filename, 'w') as f:
                json.dump(trace_log, f, cls=CustomJSONEncoder, indent=2)
                print(f"Trace log saved to {json_filename}")
            
            return json_filename
        else:
            print("No trace log to save" if not trace_log else "save_json is False")
            return None
            
    except Exception as e:
        print(f"Error in debug_line_by_line_in_test_file: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    tests_functions_path = sys.argv[1]
    test_function_name = None
    if len(sys.argv) > 2:
        test_function_name = sys.argv[2]

    debug_line_by_line_in_test_file(tests_functions_path, test_function_name)