import pytest
from generate_prompt import generate_prompt_as_string
from llm_interface import run_completion
from apply_patch import patch_code

def run_pytest(project_path):
    result = pytest.main(["-s", "-q", "--junitxml=report.xml", project_path])
    return result

def run_workflow(project_path):
    before_report = run_pytest(project_path)
    # generate_prompt
    auto_debug_path = f"{project_path}/auto_debug.json"
    prompt = generate_prompt_as_string(auto_debug_path)
    
    # query llm
    response = run_completion(prompt)

    # apply patch
    patch_code(response)

    after_report = run_pytest(project_path)

if __name__ == "__main__":
    path_to_project = ""
