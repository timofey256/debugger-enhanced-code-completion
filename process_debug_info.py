import json
import sys
import os
from typing import Dict, List, Any, Optional

def save_trace_log(trace_log: List[Dict[str, Any]], output_path: str) -> None:
    """
    Save the trace log to a JSON file.
    
    Args:
        trace_log: The trace log to save
        output_path: Path to save the JSON file
    """
    with open(output_path, 'w') as f:
        json.dump(trace_log, f, indent=2)

def extract_test_debug_info(trace_log: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract important debug information from the trace log focused on test failures.
    
    Args:
        trace_log: The trace log from debug_test_case
        
    Returns:
        Dictionary containing essential debug information
    """
    # Look for exceptions first
    exceptions = [record for record in trace_log if record.get("event") == "exception"]
    
    result = {
        "exception_events": exceptions,
        "stack_trace": [],
        "local_variables": {},
        "function_calls": [],
        "execution_path": []
    }
    
    # Extract execution path
    for record in trace_log:
        if record.get("event") == "line":
            result["execution_path"].append({
                "file": record.get("file_name", ""),
                "line": record.get("line_no", 0),
                "source": record.get("source", ""),
                "locals": record.get("locals", {})
            })
            
        elif record.get("event") == "call":
            result["function_calls"].append({
                "function": record.get("func_name", ""),
                "file": record.get("file_name", ""),
                "line": record.get("line_no", 0),
                "args": record.get("locals", {})
            })
            
        # For each exception, build a detailed stack trace
        if record.get("event") == "exception":
            # Save all local variables at the point of exception
            result["local_variables"] = record.get("locals", {})
            
            # If there's a formatted exception, parse it to extract the stack trace
            if "exception" in record:
                stack_trace = record["exception"].strip().split('\n')
                result["stack_trace"] = stack_trace
    
    return result

def main():
    """
    Process the trace log from main.py and save it as structured debug information.
    
    Usage:
        python process_debug_info.py /path/to/trace_log.json
    """
    if len(sys.argv) < 2:
        print("Usage: python process_debug_info.py /path/to/trace_log.json")
        sys.exit(1)
    
    trace_log_path = sys.argv[1]
    
    try:
        with open(trace_log_path, 'r') as f:
            trace_log = json.load(f)
    except Exception as e:
        print(f"Error loading trace log: {str(e)}")
        sys.exit(1)
    
    # Process the trace log to extract debug information
    debug_info = extract_test_debug_info(trace_log)
    
    # Save the processed information
    output_path = os.path.splitext(trace_log_path)[0] + "_processed.json"
    with open(output_path, 'w') as f:
        json.dump(debug_info, f, indent=2)
    
    print(f"Processed debug information saved to {output_path}")
    
    # If there are exceptions, display them
    if debug_info["exception_events"]:
        print("\nExceptions found:")
        for i, exception in enumerate(debug_info["exception_events"]):
            if "exception" in exception:
                print(f"\nException {i+1}:")
                print(exception["exception"])
            else:
                print(f"\nException {i+1}:")
                print(f"  File: {exception.get('file_name', 'unknown')}")
                print(f"  Line: {exception.get('line_no', 0)}")
                print(f"  Function: {exception.get('func_name', 'unknown')}")

if __name__ == "__main__":
    main()