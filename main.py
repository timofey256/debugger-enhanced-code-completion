from pathlib import Path
import os, sys, site, pytest
from typing import List, Tuple
import subprocess
from generate_prompt import generate_prompt_as_string
from llm_interface import run_completion
from apply_patch import patch_code, parse_unified_diff, DiffBlock

def extend_pythonpath(base: Path):
    for p in base.rglob("*"):
        if p.is_dir() and any(f.suffix == ".py" for f in p.iterdir()):
            sys.path.insert(0, str(p))

def run_pytest(project_root: str):
    root = Path(project_root).resolve()
    os.chdir(root)
    extend_pythonpath(root)
    os.environ["PYTHONPATH"] = os.pathsep.join(sys.path)

    pytest.main(["-s", "-q", "--junitxml", "report.xml", str(root)])
    return (root / "report.xml").read_text()

def run_pytest_as_subprocess(project_path: str):
    result = subprocess.run(
        ["pytest", "-s", "-q"],
        cwd=project_path,
        capture_output=True,
        text=True,
        check=True
    )

    return result.stdout

def get_patches(project_path: str, test_name: str) -> List[DiffBlock]:
    # generate prompt
    debug_log_path = project_path + "/auto_debug.json"
    prompt = generate_prompt_as_string(debug_log_path, test_name)

    # query LLM
    model_response = run_completion(prompt)

    # parse patches from the response
    return parse_unified_diff(model_response)

# TODO: move prints to debug mode
def run_workflow(project_path: str, test_name: str):

    # collect report of tests. this needs conftest.py inside the *tested* project root.
    try:
        run_pytest_as_subprocess(project_path) # generates auto_debug.json which we will pick up next
    except Exception as e:
        print(f"Some failures occured. Error message: \n{e}\n\n")
        print("This can mean either failed tests, or failed debugging process, so no exiting")

    # generate prompt
    debug_log_path = project_path + "/auto_debug.json"
    prompt = generate_prompt_as_string(debug_log_path, test_name)
    print(f"Prompt: {prompt}")
    print("="*150)

    # query LLM
    model_response = run_completion(prompt)
    print(f"Model response: \n {model_response}")
    print("="*150)

    # patch code
    patch_code(model_response)

    # run report after
    after  = run_pytest_as_subprocess(project_path)

if __name__ == "__main__":
    project_path = "/home/tymofii/develop/debugger-enhanced-code-completion/example/jsonschema"
    test_name = "jsonschema/tests/test_cli.py::TestCLIIntegration::test_license"
    run_workflow(project_path, test_name)
