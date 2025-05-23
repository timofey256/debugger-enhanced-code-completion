from pathlib import Path
import os, sys, site, pytest
import subprocess
from generate_prompt import generate_prompt_as_string
from llm_interface import run_completion
from apply_patch import patch_code

REPO_ROOT   = Path(__file__).resolve().parent              # /home/.../debugger-enhanced-code-completion
TEST_TARGET = REPO_ROOT / "example" / "flask"             # collect only these tests

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


def run_workflow():
    #project_path = "/home/tymofii/school/isp/debugger-enhanced-code-completion/example/flask"
    project_path = "/home/tymofii/school/isp/debugger-enhanced-code-completion/example/jsonschema"

    # run report before
    try:
        before = run_pytest_as_subprocess(project_path)
    except:
        print("interrupted?")

    # generate prompt
    debug_log_path = project_path + "/auto_debug.json"
    prompt = generate_prompt_as_string(debug_log_path)
    print("="*50)
    print("="*50)
    print(prompt)

    # query LLM
    model_response = run_completion(prompt)
    print("="*50)
    print("="*50)
    print(model_response)
    
    # patch code
    patch_code(model_response)

    # run report after
    after  = run_pytest_as_subprocess(project_path)


if __name__ == "__main__":
    run_workflow()
