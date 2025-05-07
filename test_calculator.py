"""Script to test the calculator project using automated testing infrastructure."""

import os
import sys
import re
import random
import argparse
from run_automated_testing import AutomatedCompletionTester, ModelConfig
from main import debug_line_by_line_in_test_file

class CalculatorTester(AutomatedCompletionTester):
    def __init__(self, repo_path: str, model_configs: list[ModelConfig], max_tests: int = None):
        """
        Initialize the calculator tester.
        
        Args:
            repo_path: Path to the calculator project
            model_configs: List of model configurations to test
            max_tests: Maximum number of tests to run (None for all tests)
        """
        super().__init__(repo_path, model_configs)
        self.max_tests = max_tests

    def find_test_files(self) -> list[str]:
        """Find all test files in the repository."""
        test_files = []
        test_dir = os.path.join(self.repo_path, "tests")
        if os.path.exists(test_dir):
            for file in os.listdir(test_dir):
                if file.startswith("test_") and file.endswith(".py"):
                    test_files.append(os.path.join(test_dir, file))
        
        # If max_tests is set, randomly select that many test files
        if self.max_tests and len(test_files) > self.max_tests:
            test_files = random.sample(test_files, self.max_tests)
            
        return test_files

    def extract_implementation_file(self, test_file: str) -> str:
        """Find the implementation file being tested."""
        # Get the test file name without 'test_' prefix
        test_name = os.path.basename(test_file)
        if test_name.startswith('test_'):
            impl_name = test_name[5:]  # Remove 'test_' prefix
            # Look in the src/calculator directory
            impl_path = os.path.join(self.repo_path, "src", "calculator", impl_name)
            if os.path.exists(impl_path):
                return impl_path
        return None

    def backup_original_file(self, file_path: str) -> str:
        """Create a backup of the original file."""
        backup_path = f"{file_path}.bak"
        with open(file_path, 'r') as src, open(backup_path, 'w') as dst:
            dst.write(src.read())
        return backup_path

    def restore_original_file(self, file_path: str, backup_path: str):
        """Restore the original file from backup."""
        if os.path.exists(backup_path):
            with open(backup_path, 'r') as src, open(file_path, 'w') as dst:
                dst.write(src.read())
            os.remove(backup_path)

    def run_debug_trace(self, test_file: str) -> str:
        """Run debug trace on a test file and return the path to the trace log."""
        return debug_line_by_line_in_test_file(test_file)

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Run automated testing on calculator project')
    parser.add_argument('--max-tests', type=int, help='Maximum number of tests to run')
    args = parser.parse_args()
    
    # Path to our calculator project
    repo_path = os.path.join("example", "calculator")
    
    # Add src directory to Python path for imports
    sys.path.insert(0, os.path.join(repo_path, "src"))
    
    # Configure models to test with
    model_configs = [
        #ModelConfig("deepseek-coder", temperature=0.0),
        #ModelConfig("deepseek-coder", temperature=0.2),
        ModelConfig("deepseek-coder", temperature=0.4)
    ]
    
    # Create tester instance with max_tests parameter
    tester = CalculatorTester(repo_path, model_configs, max_tests=args.max_tests)
    
    # Run evaluation
    tester.run_evaluation()

if __name__ == "__main__":
    main() 