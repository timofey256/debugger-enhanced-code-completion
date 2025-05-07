import os
import re
import sys
import ast
import json
import difflib
import inspect
import importlib
import subprocess
import concurrent.futures
from typing import Dict, List, Tuple, Optional, Any
from Levenshtein import distance as levenshtein_distance
import random
import pytest
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ModelConfig:
    """Configuration for a model to test."""
    name: str
    temperature: float = 0.0
    max_tokens: int = 2048
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0

class TestResult:
    """Class to store test results."""
    def __init__(self):
        self.passed_tests_before: int = 0
        self.passed_tests_after: int = 0
        self.total_tests: int = 0
        self.edit_distances: Dict[str, float] = {}
        self.normalized_distances: Dict[str, float] = {}
        self.execution_time: float = 0.0
        self.error_messages: List[str] = []

class AutomatedCompletionTester:
    def __init__(self, repo_path: str, model_configs: List[ModelConfig]):
        self.repo_path = repo_path
        self.model_configs = model_configs
        self.results: Dict[str, Dict[str, TestResult]] = {}  # test_file -> model_name -> TestResult
        
    def find_test_files(self) -> List[str]:
        """Find all test files in the repository."""
        test_files = []
        for root, _, files in os.walk(self.repo_path):
            for file in files:
                if file.startswith("test_") and file.endswith(".py"):
                    test_files.append(os.path.join(root, file))
        return test_files
    
    def extract_implementation_file(self, test_file: str) -> Optional[str]:
        """Find the implementation file being tested."""
        with open(test_file, 'r') as f:
            content = f.read()
        
        # Parse imports to find the implementation file
        imports = re.findall(r'(?:from|import)\s+([\w.]+)', content)
        for imp in imports:
            # Remove 'test_' prefix if present in the import
            candidate = imp.replace('test_', '')
            # Look in src/calculator directory
            candidate_path = os.path.join(self.repo_path, "src", "calculator", f"{candidate}.py")
            if os.path.exists(candidate_path):
                return candidate_path
        return None
    
    def backup_original_file(self, file_path: str) -> str:
        """Create a backup of the original file."""
        backup_path = f"{file_path}.bak"
        with open(file_path, 'r') as src, open(backup_path, 'w') as dst:
            dst.write(src.read())
        return backup_path
    
    def replace_with_not_implemented(self, file_path: str) -> Dict[str, str]:
        """Replace functions with NotImplementedError and return original code using AST."""
        original_functions = {}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # First collect line by line content to recreate the file
            lines = content.splitlines(True)  # Keep line endings
            
            # Parse the file with AST
            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                print(f"Syntax error in {file_path}: {e}")
                return {}
            
            # Track functions to replace
            replacements = []
            
            # Visitor to collect all function definitions
            class FunctionVisitor(ast.NodeVisitor):
                def __init__(self):
                    self.current_class = None
                    
                def visit_ClassDef(self, node):
                    old_class = self.current_class
                    self.current_class = node.name
                    
                    # Process class body
                    for item in node.body:
                        self.visit(item)
                    
                    self.current_class = old_class
                
                def visit_FunctionDef(self, node):
                    # Get function name, with class name if it's a method
                    if self.current_class:
                        qualified_name = f"{self.current_class}.{node.name}"
                    else:
                        qualified_name = node.name
                    
                    # Get the exact source code for this function
                    start_line = node.lineno - 1  # Convert to 0-based indexing
                    end_line = node.end_lineno  # already 0-based indexing
                    
                    # Find where the function body starts (after the colon)
                    body_start_line = None
                    for i in range(start_line, end_line):
                        if '):' in lines[i] or "->" in lines[i]:
                            body_start_line = i
                            break
                    
                    if body_start_line is None:
                        print(f"Could not find function body start for {qualified_name}")
                        return
                    
                    # Capture original code
                    func_source = ''.join(lines[start_line:end_line])
                    original_functions[qualified_name] = func_source
                    
                    # Create replacement node info
                    replacements.append({
                        'start_line': start_line,
                        'end_line': end_line,
                        'body_start_line': body_start_line,
                        'name': node.name,
                        'qualified_name': qualified_name,
                        'indent': len(lines[start_line]) - len(lines[start_line].lstrip()),
                        'signature_lines': lines[start_line:body_start_line + 1]  # Include the line with colon
                    })
                    
                    # Visit function body to find nested functions
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            # For nested functions, provide parent context
                            old_class = self.current_class
                            self.current_class = None  # Reset class context for nested functions
                            self.visit(item)
                            self.current_class = old_class
            
            # Run the visitor
            visitor = FunctionVisitor()
            visitor.visit(tree)
            
            # Apply replacements in reverse order (to avoid line number shifts)
            replacements.sort(key=lambda r: r['start_line'], reverse=True)
            
            #def replace_function_with_todo_exception(replacement):
            for replacement in replacements:
                # Preserve the entire function signature (including multi-line signatures)
                signature_lines = replacement['signature_lines']
                indent = ' ' * replacement['indent']
                
                # Replace only the function body with NotImplementedError, keeping the signature intact
                new_content = []
                new_content.extend(signature_lines)  # Keep the entire signature
                new_content.append(f"{indent}    raise NotImplementedError('TODO')\n\n")
                
                # Replace the entire function with our new version
                lines[replacement['start_line']:replacement['end_line']] = new_content

            # REPLACES EVERY FUNCTION 
           # for replacement in replacements:
           #    replace_function_with_todo_exception(replacement)

           # # REPLACES RANDOM FUNCTION
           ## if not len(replacements):
           ##     return original_functions

           # replace_function_with_todo_exception(random.choice(replacements))
            
            # Write modified content back
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            return original_functions
        except Exception as e:
            print(f"Error processing file {file_path}: {str(e)}")
            import traceback
            traceback.print_exc()
            return {}
    
    def run_debug_trace(self, test_file: str) -> str:
        """Run the debug trace on a test file and return the trace log path."""
        result = subprocess.run(
            [sys.executable, "main.py", test_file],
            capture_output=True,
            text=True
        )
        
        # Extract the generated JSON file path from output
        match = re.search(r'Trace log saved to (.*\.json)', result.stdout)
        if match:
            return match.group(1)
        return None
    
    def generate_completion(self, trace_log_path: str, model_config: ModelConfig) -> str:
        """Generate code completion using the model with specific configuration."""
        print(f"Generating completion for {trace_log_path} with model {model_config.name}")
        
        # Create a temporary config file
        config = {
            "model": model_config.name,
            "temperature": model_config.temperature,
            "max_tokens": model_config.max_tokens,
            "top_p": model_config.top_p,
            "frequency_penalty": model_config.frequency_penalty,
            "presence_penalty": model_config.presence_penalty
        }
        
        config_path = f"model_config_{model_config.name}.json"
        with open(config_path, 'w') as f:
            json.dump(config, f)
        
        try:
            print(f"Running completion_model.py with trace log: {trace_log_path}")
            result = subprocess.run(
                [sys.executable, "completion_model.py", trace_log_path, "--config", config_path],
                capture_output=True,
                text=True
            )
            print(f"completion_model.py output: {result.stdout}")
            if result.stderr:
                print(f"completion_model.py errors: {result.stderr}")
            
            # Find the generated code file
            code_dir = "code_completion_results"
            if not os.path.exists(code_dir):
                print(f"Code completion directory {code_dir} does not exist")
                return None
            
            files = os.listdir(code_dir)
            if not files:
                print("No completion files found")
                return None
            
            files.sort(key=lambda x: os.path.getmtime(os.path.join(code_dir, x)), reverse=True)
            completion_path = os.path.join(code_dir, files[0])
            print(f"Found completion file: {completion_path}")
            return completion_path

            return None
        finally:
            # Clean up config file
            if os.path.exists(config_path):
                os.remove(config_path)

    def calculate_metrics(self, original_functions: Dict[str, str], completion_path: str) -> Dict[str, float]:
        """Calculate edit distance between original and generated code."""
        with open(completion_path, 'r') as f:
            generated_code = f.read()
            
        metrics = {}
        for func_name, original_code in original_functions.items():
            # Extract the function from the generated code
            func_pattern = rf'def\s+{func_name}\s*\([^)]*\)[^:]*:(.*?)(?=def|\Z)'
            match = re.search(func_pattern, generated_code, re.DOTALL)
            if match:
                generated_func = match.group(0)
                # Calculate edit distance
                dist = levenshtein_distance(original_code, generated_func)
                metrics[func_name] = {
                    'edit_distance': dist,
                    'normalized_distance': dist / len(original_code)
                }
                
        return metrics
    
    def restore_original_file(self, file_path: str, backup_path: str):
        """Restore the original file from backup."""
        with open(backup_path, 'r') as src, open(file_path, 'w') as dst:
            dst.write(src.read())
        os.remove(backup_path)
    
    def run_tests(self, test_file: str) -> Tuple[int, int]:
        """Run tests and return (passed_tests, total_tests)."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_file, "-v"],
                capture_output=True,
                text=True
            )
            
            # Parse test results
            passed = len(re.findall(r'PASSED', result.stdout))
            total = len(re.findall(r'(PASSED|FAILED|ERROR)', result.stdout))
            return passed, total
        except Exception as e:
            print(f"Error running tests: {str(e)}")
            return 0, 0

    def run_evaluation(self, max_workers: int = 4):
        """Run the full evaluation pipeline with parallel processing."""
        test_files = self.find_test_files()
        
        # Create a thread pool for parallel processing
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all test files for processing
            future_to_test = {
                executor.submit(self.process_test_file, test_file): test_file 
                for test_file in test_files
            }
            
            # Process results as they complete
            for future in concurrent.futures.as_completed(future_to_test):
                test_file = future_to_test[future]
                try:
                    result = future.result()
                    if result:
                        self.results[test_file] = result
                except Exception as e:
                    print(f"Error processing {test_file}: {str(e)}")
        
        # Generate summary report
        self._generate_report()

    def process_test_file(self, test_file: str) -> Optional[Dict[str, TestResult]]:
        """Process a single test file with all model configurations."""
        print(f"Processing test file: {test_file}")
        
        # Find the implementation file
        impl_file = self.extract_implementation_file(test_file)
        if not impl_file:
            print(f"Could not find implementation file for {test_file}")
            return None
            
        # Backup original file
        backup_path = self.backup_original_file(impl_file)
        
        try:
            # Get initial test results
            passed_before, total_tests = self.run_tests(test_file)
            
            # Replace functions with NotImplementedError
            original_functions = self.replace_with_not_implemented(impl_file)
            
            # Process with each model configuration
            model_results = {}
            for model_config in self.model_configs:
                start_time = datetime.now()
                
                # Run debug trace
                trace_log_path = self.run_debug_trace(test_file)
                if not trace_log_path:
                    print(f"Failed to generate trace log for {test_file} with model {model_config.name}")
                    continue
                
                # Generate completion
                completion_path = self.generate_completion(trace_log_path, model_config)
                if not completion_path:
                    print(f"Failed to generate completion for {test_file} with model {model_config.name}")
                    continue
                
                # Apply the completion to the implementation file
                with open(completion_path, 'r') as f:
                    completion_code = f.read()
                with open(impl_file, 'w') as f:
                    f.write(completion_code)
                
                # Calculate metrics
                metrics = self.calculate_metrics(original_functions, completion_path)
                
                # Run tests with generated code
                passed_after, _ = self.run_tests(test_file)
                
                # Create test result
                result = TestResult()
                result.passed_tests_before = passed_before
                result.passed_tests_after = passed_after
                result.total_tests = total_tests
                result.edit_distances = {k: v['edit_distance'] for k, v in metrics.items()}
                result.normalized_distances = {k: v['normalized_distance'] for k, v in metrics.items()}
                result.execution_time = (datetime.now() - start_time).total_seconds()
                
                model_results[model_config.name] = result
            
            return model_results
            
        finally:
            # Always restore the original file
            self.restore_original_file(impl_file, backup_path)

    def _generate_report(self):
        """Generate a detailed summary report of the evaluation."""
        if not self.results:
            print("No results!")
            return None

        report = {
            'timestamp': datetime.now().isoformat(),
            'models': [config.name for config in self.model_configs],
            'test_files': len(self.results),
            'summary': {},
            'detailed_results': {}
        }
        
        # Calculate summary statistics for each model
        for model_config in self.model_configs:
            model_name = model_config.name
            model_results = [r[model_name] for r in self.results.values() if model_name in r]
            
            if not model_results:
                continue
                
            # Calculate total edit distances
            total_edit_distances = sum(
                sum(r.edit_distances.values()) for r in model_results if r.edit_distances
            )
            total_edit_distance_count = sum(
                len(r.edit_distances) for r in model_results if r.edit_distances
            )
            
            # Calculate total normalized distances
            total_normalized_distances = sum(
                sum(r.normalized_distances.values()) for r in model_results if r.normalized_distances
            )
            total_normalized_distance_count = sum(
                len(r.normalized_distances) for r in model_results if r.normalized_distances
            )
            
            summary = {
                'total_tests': sum(r.total_tests for r in model_results),
                'total_passed_before': sum(r.passed_tests_before for r in model_results),
                'total_passed_after': sum(r.passed_tests_after for r in model_results),
                'average_edit_distance': total_edit_distances / total_edit_distance_count if total_edit_distance_count > 0 else 0,
                'average_normalized_distance': total_normalized_distances / total_normalized_distance_count if total_normalized_distance_count > 0 else 0,
                'average_execution_time': sum(r.execution_time for r in model_results) / len(model_results),
                'test_improvement_rate': sum(
                    1 for r in model_results if r.passed_tests_after > r.passed_tests_before
                ) / len(model_results)
            }
            
            report['summary'][model_name] = summary
        
        # Add detailed results
        for test_file, model_results in self.results.items():
            report['detailed_results'][test_file] = {
                model_name: {
                    'passed_tests_before': r.passed_tests_before,
                    'passed_tests_after': r.passed_tests_after,
                    'total_tests': r.total_tests,
                    'edit_distances': r.edit_distances,
                    'normalized_distances': r.normalized_distances,
                    'execution_time': r.execution_time,
                    'error_messages': r.error_messages
                }
                for model_name, r in model_results.items()
            }
        
        # Save the report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = f'evaluation_report_{timestamp}.json'
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
            
        print(f"Evaluation complete. Report saved to {report_path}")
        
        # Print summary to console
        print("\nEvaluation Summary:")
        print("==================")
        for model_name, summary in report['summary'].items():
            print(f"\nModel: {model_name}")
            print(f"Total Tests: {summary['total_tests']}")
            print(f"Tests Passed Before: {summary['total_passed_before']}")
            print(f"Tests Passed After: {summary['total_passed_after']}")
            print(f"Test Improvement Rate: {summary['test_improvement_rate']:.2%}")
            print(f"Average Edit Distance: {summary['average_edit_distance']:.2f}")
            print(f"Average Normalized Distance: {summary['average_normalized_distance']:.2f}")
            print(f"Average Execution Time: {summary['average_execution_time']:.2f}s")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_automated_testing.py <repo_path> [model_configs...]")
        repo_path = "/home/tymofii/school/isp/debugger-enhanced-code-completion/example/flask"
    else:
        repo_path = sys.argv[1]
    
    # Default model configurations
    model_configs = [
        ModelConfig("deepseek-coder", temperature=0.0),
        ModelConfig("deepseek-coder", temperature=0.2),
        ModelConfig("deepseek-coder", temperature=0.4)
    ]
    
    # Override with command line arguments if provided
    if len(sys.argv) > 2:
        model_configs = []
        for config in sys.argv[2:]:
            try:
                model_name, temp = config.split(':')
                model_configs.append(ModelConfig(model_name, temperature=float(temp)))
            except ValueError:
                print(f"Invalid model configuration: {config}")
                sys.exit(1)
    
    tester = AutomatedCompletionTester(repo_path, model_configs)
    tester.run_evaluation()