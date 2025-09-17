import os
import sys
import json
from typing import Dict, List, Any
import json
import time

from .llm_interface import LLMInterface

class CompletionModelBuilder:
    """
    A model that processes debug information from stack traces and prepares
    context for LLM-based code completion.
    """
    
    def __init__(self, trace_log: List[Dict[str, Any]]):
        """
        Initialize with debug trace log from main.py.
        
        Args:
            trace_log: Debug information collected by the debugger
        """
        self.trace_log = trace_log
        self.exception_events = self._find_exception_events()
        self.relevant_code_blocks = {}
        
    def _find_exception_events(self) -> List[Dict[str, Any]]:
        """Find all exception events in the trace log."""
        return [record for record in self.trace_log if record.get("event") == "exception"]
    
    def _extract_full_traceback(self, exception_record: Dict[str, Any]) -> str:
        """Extract the full traceback from an exception record."""
        if "exception" in exception_record:
            return exception_record["exception"]
        return "No detailed traceback available"
    
    def _collect_frames_before_exception(self, exception_index: int, context_lines: int = 10) -> List[Dict[str, Any]]:
        """
        Collect the n frames before an exception occurred to provide context.
        
        Args:
            exception_index: Index of the exception event in the trace log
            context_lines: Number of frames to collect before the exception
            
        Returns:
            List of trace records leading up to the exception
        """
        start_idx = max(0, exception_index - context_lines)
        return self.trace_log[start_idx:exception_index]
    
    def _extract_source_from_file(self, file_name: str, line_no: int, context_lines: int = None) -> str:
        """
        Extract source code from a file.
        
        Args:
            file_name: Path to the source file
            line_no: Line number where code is needed (for highlighting)
            context_lines: Number of lines before and after to include (None for entire file)
            
        Returns:
            Source code with context
        """
        if not os.path.exists(file_name):
            return f"# File not found: {file_name}"
            
        try:
            with open(file_name, 'r') as f:
                lines = f.readlines()
                
            if context_lines is None:
                # Return entire file
                result = []
                for i, line in enumerate(lines, 1):
                    prefix = "→ " if i == line_no else "  "
                    result.append(f"{prefix}{i}: {line}")
                return "".join(result)
            else:
                # Return context window
                start = max(0, line_no - context_lines - 1)
                end = min(len(lines), line_no + context_lines)
                
                # Format with line numbers
                result = []
                for i, line in enumerate(lines[start:end], start + 1):
                    prefix = "→ " if i == line_no else "  "
                    result.append(f"{prefix}{i}: {line}")
                    
                return "".join(result)
        except Exception as e:
            return f"# Error reading file: {str(e)}"
    
    def analyze_exceptions(self) -> None:
        """Analyze all exceptions found in the trace log."""
        for i, exception in enumerate(self.exception_events):
            # Find the index of this exception in the original trace log
            exception_index = self.trace_log.index(exception)
            
            # Extract key information
            traceback_text = self._extract_full_traceback(exception)
            frames_before = self._collect_frames_before_exception(exception_index)
            
            # Get the source code from the file where the exception occurred
            if "file_name" in exception and "line_no" in exception:
                source_code = self._extract_source_from_file(
                    exception["file_name"], 
                    exception["line_no"],
                    context_lines=None  # Get entire file
                )
            else:
                source_code = "# Source code not available"
            
            # Store the relevant code blocks
            self.relevant_code_blocks[f"exception_{i}"] = {
                "exception_details": exception,
                "traceback": traceback_text,
                "context_frames": frames_before,
                "source_code": source_code,
                "local_variables": exception.get("locals", {})
            }
    
    def build_completion_request(self, include_all_exceptions: bool = True) -> Dict[str, Any]:
        """
        Build a request for the LLM to complete missing code based on exceptions.
        
        Args:
            include_all_exceptions: Whether to include all exceptions or just the first one
            
        Returns:
            Dictionary with context for the LLM request
        """
        if not self.exception_events:
            return {"error": "No exceptions found in the trace log"}
            
        # Ensure we've analyzed exceptions
        if not self.relevant_code_blocks:
            self.analyze_exceptions()
        
        # Build the context for the completion request
        completion_context = {
            "task": "complete_missing_code",
            "num_exceptions": len(self.exception_events),
            "exceptions": []
        }
        
        # Process all exceptions
        for i in range(len(self.exception_events)):
            exception_key = f"exception_{i}"
            if exception_key not in self.relevant_code_blocks:
                continue
                
            exception_data = self.relevant_code_blocks[exception_key]
            
            exception_info = {
                "exception_type": self._extract_exception_type(exception_data["traceback"]),
                "exception_message": self._extract_exception_message(exception_data["traceback"]),
                "source_code": exception_data["source_code"],
                "traceback": exception_data["traceback"],
                "relevant_variables": self._filter_relevant_variables(exception_data["local_variables"]),
                "execution_context": self._summarize_execution_context(exception_data["context_frames"]),
                "related_code": self._extract_related_code(exception_data["traceback"]),
                "class_context": exception_data["exception_details"].get("class_context", {})
            }
            
            completion_context["exceptions"].append(exception_info)
        
        # Add code from all files in the stack traces to provide a comprehensive view
        all_related_code = {}
        for exception_info in completion_context["exceptions"]:
            for file_path, code in exception_info["related_code"].items():
                if file_path not in all_related_code:
                    all_related_code[file_path] = code
        
        completion_context["all_related_code"] = all_related_code
        
        return completion_context
    
    def _extract_exception_type(self, traceback_text: str) -> str:
        """Extract the exception type from a traceback."""
        lines = traceback_text.strip().split('\n')
        if lines and len(lines) > 1:
            last_line = lines[-1]
            exception_type = last_line.split(':')[0]
            return exception_type
        return "Unknown"
    
    def _extract_exception_message(self, traceback_text: str) -> str:
        """Extract the exception message from a traceback."""
        lines = traceback_text.strip().split('\n')
        if lines and len(lines) > 1:
            last_line = lines[-1]
            if ':' in last_line:
                return last_line.split(':', 1)[1].strip()
        return "No detailed message"
    
    def _filter_relevant_variables(self, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Filter out only the variables that seem relevant to the exception."""
        # For now, return all variables - in a real implementation, you might
        # want to filter based on what's used in the failing line
        return variables
    
    def _summarize_execution_context(self, frames: List[Dict[str, Any]]) -> str:
        """Create a summary of the execution context leading to the exception."""
        summary = []
        
        for frame in frames:
            if frame.get("event") == "call":
                summary.append(f"Entered function {frame.get('func_name', 'unknown')}")
            elif frame.get("event") == "line":
                if "source" in frame and frame["source"].strip():
                    summary.append(f"Executed: {frame.get('source', '')}")
            elif frame.get("event") == "return":
                summary.append(f"Returned from {frame.get('func_name', 'unknown')} with value {frame.get('arg', 'unknown')}")
        
        return "\n".join(summary)
    
    def _extract_related_code(self, traceback_text: str) -> Dict[str, str]:
        """Extract code from files referenced in the traceback."""
        files_mentioned = {}
        
        # Parse the traceback to find file paths and line numbers
        lines = traceback_text.strip().split('\n')
        for line in lines:
            if 'File "' in line and '", line' in line:
                parts = line.split('File "', 1)[1].split('", line')
                if len(parts) >= 2:
                    file_path = parts[0]
                    line_no = int(parts[1].split(',')[0])
                    
                    # Only include files from the calculator repository
                    if os.path.exists(file_path) and 'calculator' in file_path and file_path not in files_mentioned:
                        files_mentioned[file_path] = self._extract_source_from_file(file_path, line_no, context_lines=None)
        
        return files_mentioned
    
    def create_llm_request(self, include_all_exceptions: bool = True) -> str:
        """
        Generate a request string to send to the LLM for code completion.
        
        Args:
            include_all_exceptions: Whether to include all exceptions or just the first one
            
        Returns:
            Formatted string ready to send to the LLM
        """
        context = self.build_completion_request(include_all_exceptions)
        
        if "error" in context:
            return f"Error preparing LLM request: {context['error']}"
        
        # Format the request as a clear prompt for the LLM
        prompt = f"""
You are an AI coding assistant tasked with implementing missing code based on debug information.

# OVERVIEW
Total Exceptions Found: {context['num_exceptions']}

"""
        
        # Add each exception's details
        for i, exception in enumerate(context['exceptions']):
            prompt += f"""
# EXCEPTION {i+1} INFORMATION
Type: {exception['exception_type']}
Message: {exception['exception_message']}

## FAILING CODE - EXCEPTION {i+1}
```python
{exception['source_code']}
```

## TRACEBACK - EXCEPTION {i+1}
```
{exception['traceback']}
```

## EXECUTION CONTEXT - EXCEPTION {i+1}
```
{exception['execution_context']}
```

## VARIABLE VALUES AT EXCEPTION TIME - EXCEPTION {i+1}
```
{json.dumps(exception['relevant_variables'], indent=2)}
```

## CLASS API CONTEXT - EXCEPTION {i+1}
```
{json.dumps(exception.get('class_context', {}), indent=2)}
```

"""
        
        prompt += f"""
# ALL RELATED CODE FROM CALL STACKS
{self._format_related_code(context['all_related_code'])}

Based on the information above, please:
1. Identify all functions that need to be implemented (including those with NotImplementedError)
2. Provide a complete implementation of ALL functions that would pass the tests
3. Make sure to implement ALL functions, not just the ones that had exceptions
4. Explain your reasoning for the implementations

```python
# Your implementation here
```
"""
        return prompt
    
    def _format_related_code(self, related_code: Dict[str, str]) -> str:
        """Format the related code sections for the LLM prompt."""
        if not related_code:
            return "No related code found"
            
        sections = []
        for file_path, code in related_code.items():
            sections.append(f"## File: {file_path}\n```python\n{code}\n```")
            
        return "\n\n".join(sections)

def log_prompt(request, prompt_logged_dir="prompt_log"):
    timestamp = int(time.time())

    os.makedirs(prompt_logged_dir, exist_ok=True)
    prompt_logged_path = f"{prompt_logged_dir}/prompt_{timestamp}.txt"
    
    with open(prompt_logged_path, 'w') as f:
        f.write(request)

def log_code_completion(request, code_completion_dir="code_completion_results"):
    timestamp = int(time.time())

    os.makedirs(code_completion_dir, exist_ok=True)
    prompt_logged_path = f"{code_completion_dir}/code_{timestamp}.py"
    
    with open(prompt_logged_path, 'w') as f:
        f.write(request)

def main():
    """
    Process debug trace log and create an LLM completion request.
    
    Usage:
        python completion_model.py /path/to/trace_log.json
    """
    if len(sys.argv) < 2:
        print("Usage: python completion_model.py /path/to/trace_log.json")
        sys.exit(1)
    
    #trace_log_path = "/home/tymofii/school/isp/debugger-enhanced-code-completion/experiment_runs/trace_test_cli.py_test_help_echo_exception_1744640679.json" 
    trace_log_path = sys.argv[1] 
    
    try:
        with open(trace_log_path, 'r') as f:
            trace_log = json.load(f)
    except Exception as e:
        print(f"Error loading trace log: {str(e)}")
        sys.exit(1)
    
    model = CompletionModelBuilder(trace_log)
    request = model.create_llm_request()

    llm = LLMInterface()
    response = llm.complete_code(request)
    
    code = llm.extract_code_from_response(response)
    
    log_prompt(request)
    log_code_completion(code)

    print("Done.")

if __name__ == "__main__":
    main()
