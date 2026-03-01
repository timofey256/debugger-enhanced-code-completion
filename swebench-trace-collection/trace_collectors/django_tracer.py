"""
Django test tracer - hooks into Django's test runner.

Django uses its own test discovery and runner (DiscoverRunner),
which wraps unittest but creates test results at runtime.
We need to patch Django's runner specifically.
"""

import json
import os
import sys
import sysconfig
import unittest
from typing import Any, Dict

# Cutoff for variable serialization
CUTOFF_OFFSET = 1000
HAS_JSONPICKLE = False

try:
    import jsonpickle
    HAS_JSONPICKLE = True
except ImportError:
    pass


class DebugTestResult(unittest.TestResult):
    """
    Custom TestResult that captures exception details.

    Works by overriding stopTestRun() to process all errors/failures
    that unittest has already collected.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.debug_store = []

        # Get stdlib paths for filtering
        self._stdlib_paths = [
            sysconfig.get_path("stdlib"),
            sysconfig.get_path("platstdlib"),
            sys.prefix,
            sys.base_prefix,
        ]
        self._stdlib_paths = [p for p in self._stdlib_paths if p]

    def stopTestRun(self):
        """
        Process all errors/failures after test run completes.

        This is called ONCE at the end, similar to pytest_sessionfinish.
        """
        super().stopTestRun()

        # Process errors (exceptions)
        for test, traceback_str in self.errors:
            self._capture_from_string(test, traceback_str, "ERROR")

        # Process failures (assertion errors)
        for test, traceback_str in self.failures:
            self._capture_from_string(test, traceback_str, "FAIL")

        # Write to file
        self._write_traces()

    def _capture_from_string(self, test, traceback_str: str, status: str):
        """
        Extract trace info from traceback string.

        unittest stores tracebacks as formatted strings, not exception objects.
        We parse the string to extract file/line/function info.
        """
        # Parse the traceback string
        lines = traceback_str.strip().split('\n')

        # Extract exception type and message (last line)
        exc_info = lines[-1] if lines else "Unknown error"
        exc_parts = exc_info.split(':', 1)
        exc_type = exc_parts[0].strip() if exc_parts else "Error"
        exc_message = exc_parts[1].strip() if len(exc_parts) > 1 else ""

        # Extract frames from traceback
        frames = []
        i = 0
        while i < len(lines):
            line = lines[i]

            # Look for "File" lines
            if line.strip().startswith('File "'):
                # Extract file and line number
                # Format: File "/path/to/file.py", line 123, in function_name
                try:
                    # Parse file path
                    file_start = line.index('"') + 1
                    file_end = line.index('"', file_start)
                    filepath = line[file_start:file_end]

                    # Parse line number
                    line_part = line[file_end:]
                    if ', line ' in line_part:
                        line_num_start = line_part.index(', line ') + 7
                        line_num_end = line_part.index(',', line_num_start)
                        line_num = int(line_part[line_num_start:line_num_end])
                    else:
                        line_num = 0

                    # Parse function name
                    if ', in ' in line_part:
                        func_start = line_part.index(', in ') + 5
                        func_name = line_part[func_start:].strip()
                    else:
                        func_name = "<module>"

                    # Only include application code
                    if self._should_include_file(filepath):
                        # Get the code line if available (next line in traceback)
                        code_line = ""
                        if i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            if not next_line.startswith('File "'):
                                code_line = next_line

                        frames.append({
                            "file": filepath,
                            "line": line_num,
                            "func": func_name,
                            "code": code_line,
                            "locals": {}  # Can't extract locals from string traceback
                        })

                except (ValueError, IndexError) as e:
                    # Skip malformed lines
                    pass

            i += 1

        # Store the trace
        if frames:  # Only store if we found application frames
            self.debug_store.append({
                "nodeid": str(test),
                "exc_type": exc_type,
                "message": exc_message,
                "frames": frames
            })

    def _should_include_file(self, filepath: str) -> bool:
        """Filter out stdlib, site-packages, and test framework internals."""
        # Skip special files
        skip_substrings = ["<", "frozen", "site-packages", "unittest", "_unittest", "/opt/tracers"]
        if any(s in filepath for s in skip_substrings):
            return False

        # Skip stdlib
        for stdlib_path in self._stdlib_paths:
            if filepath.startswith(stdlib_path):
                return False

        return True

    def _write_traces(self):
        """Write debug information to JSON file."""
        output_path = os.getenv("AUTO_DEBUG_JSON", "auto_debug.json")

        try:
            with open(output_path, 'w') as f:
                json.dump(self.debug_store, f, indent=2)

            print(f"\n▶ Debug info written to {output_path} ({len(self.debug_store)} failures)", file=sys.stderr)
        except Exception as e:
            print(f"\n✖ Failed to write debug info: {e}", file=sys.stderr)


def inject_django_tracer():
    """
    Patch Django's test runner to use our DebugTestResult.
    
    Django uses django.test.runner.DiscoverRunner which creates test results.
    We need to patch it to use our custom result class.
    
    This uses an import hook to patch Django WHEN it's imported, not before.
    """
    try:
        # First, patch unittest as a baseline
        import unittest as unittest_module
        unittest_module.TestResult = DebugTestResult
        unittest_module.TextTestRunner.resultclass = DebugTestResult
        
        # Patch unittest.result module
        try:
            import unittest.result as unittest_result_module
            unittest_result_module.TestResult = DebugTestResult
        except (ImportError, AttributeError):
            pass
        
        print("DEBUG: Base unittest patched with DebugTestResult", file=sys.stderr)
        
        # Install import hook to patch Django when it loads
        import sys
        from importlib.machinery import ModuleSpec
        from importlib.abc import MetaPathFinder, Loader
        
        class DjangoTestRunnerPatcher(MetaPathFinder):
            """Import hook to patch Django's test runner when it's imported."""
            
            def find_spec(self, fullname, path, target=None):
                """Intercept django.test.runner imports."""
                if fullname == "django.test.runner":
                    # Don't intercept, just let it load normally
                    # We'll patch it in find_module via exec_module
                    return None
                return None
            
            def find_module(self, fullname, path=None):
                """Legacy import hook for older Python versions."""
                if fullname == "django.test.runner":
                    return self
                return None
            
            def load_module(self, fullname):
                """Load and patch django.test.runner module."""
                # First, import normally
                import importlib
                module = importlib.import_module(fullname)
                
                # Now patch it
                try:
                    if hasattr(module, 'DiscoverRunner'):
                        # Patch get_resultclass method
                        original_get_resultclass = module.DiscoverRunner.get_resultclass
                        
                        def patched_get_resultclass(self):
                            """Return our DebugTestResult."""
                            return DebugTestResult
                        
                        module.DiscoverRunner.get_resultclass = patched_get_resultclass
                        print("DEBUG: Django DiscoverRunner.get_resultclass patched!", file=sys.stderr)
                except Exception as e:
                    print(f"DEBUG: Could not patch Django runner: {e}", file=sys.stderr)
                
                return module
        
        # Install the import hook
        sys.meta_path.insert(0, DjangoTestRunnerPatcher())
        print("DEBUG: Django import hook installed", file=sys.stderr)
        
        # Also try to patch Django directly if it's already imported
        if "django.test.runner" in sys.modules:
            django_runner = sys.modules["django.test.runner"]
            if hasattr(django_runner, 'DiscoverRunner'):
                original_get_resultclass = django_runner.DiscoverRunner.get_resultclass
                
                def patched_get_resultclass(self):
                    """Return our DebugTestResult."""
                    return DebugTestResult
                
                django_runner.DiscoverRunner.get_resultclass = patched_get_resultclass
                print("DEBUG: Django runner already loaded, patched directly", file=sys.stderr)
        
    except Exception as e:
        print(f"ERROR: Failed to inject Django tracer: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
