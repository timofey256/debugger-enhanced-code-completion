import ast
import os
import shutil
import tempfile
import subprocess
from debug_capture import Debugger
from mock_llm import complete_with_mock_llm

def replace_function_with_pass(source_path: str, func_name: str) -> str:
    with open(source_path, "r") as f:
        source_code = f.read()

    tree = ast.parse(source_code)

    class FunctionStubber(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            if node.name == func_name:
                node.body = [ast.Pass()]
            return node

    stubber = FunctionStubber()
    new_tree = stubber.visit(tree)
    ast.fix_missing_locations(new_tree)

    temp_dir = tempfile.mkdtemp()
    new_path = os.path.join(temp_dir, os.path.basename(source_path))

    with open(new_path, "w") as f:
        f.write(ast.unparse(new_tree))

    return new_path


def run_pytest_with_debugger(test_file: str, func_file: str, func_name: str) -> list[dict]:
    dbg = Debugger(target_func=func_name)
    return dbg.run_and_capture(test_file, func_file)


def build_prompt(signature: str, tests: str, debug_info: list[dict]) -> str:
    prompt = f"""You are writing a Python function.

Function Signature:
{signature}

Tests:
{tests}

Debugging Info:"""

    for i, trace in enumerate(debug_info):
        prompt += f"\n\nTest case {i + 1}:\n"
        for step in trace["steps"]:
            prompt += f"  Line {step['line']}: locals = {step['locals']}\n"
        if trace["exception"]:
            prompt += f"  Exception: {trace['exception']}\n"
        else:
            prompt += f"  Return: {trace['return']}\n"

    return prompt


def complete_function(signature: str, source_path: str, func_name: str, test_path: str):
    stub_path = replace_function_with_pass(source_path, func_name)
    debug_data = run_pytest_with_debugger(test_path, stub_path, func_name)

    with open(test_path, "r") as f:
        tests = f.read()

    prompt = build_prompt(signature, tests, debug_data)
    return complete_with_mock_llm(prompt)
