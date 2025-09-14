import os
import sys
from pathlib import Path
from typing import List
from flask import Flask, request, jsonify

from generate_prompt import generate_prompt_as_string
from llm_interface import run_completion
from apply_patch import parse_unified_diff, DiffBlock

PROJECT_PATH: str | None = None

app = Flask(__name__)

def to_jsonable(patches):
    """Convert your tuple/Path-based patches to plain JSON."""
    jsonable = []
    for path, hunks in patches:
        item = {
            "path": str(path),
            "hunks": []
        }
        for (old_start, old_len, new_start, new_len, lines) in hunks:
            item["hunks"].append({
                "old_start": int(old_start),
                "old_len": int(old_len),
                "new_start": int(new_start),
                "new_len": int(new_len),
                "lines": [str(s) for s in lines]
            })
        jsonable.append(item)
    return jsonable

def build_unified_diff(patches_json):
    """Assemble a valid unified diff for all files/hunks."""
    out = []

    for fp in patches_json:
        abs_path = Path(fp["path"])

        aps = str(abs_path)
        a_path = f"a{aps}" if aps.startswith("/") else f"a/{aps}"
        b_path = f"b{aps}" if aps.startswith("/") else f"b/{aps}"
        out.append(f"diff --git {a_path} {b_path}")
        out.append(f"--- {a_path}")
        out.append(f"+++ {b_path}")

        for h in fp["hunks"]:
            old_start = h["old_start"]
            old_len   = h["old_len"]
            new_start = h["new_start"]
            new_len   = h["new_len"]
            out.append(f"@@ -{old_start},{old_len} +{new_start},{new_len} @@")

            for line in h["lines"]:
                if line.startswith(("+", "-")):
                    out.append(line)
                else:
                    out.append(f" {line}")
        if not out[-1].endswith("\n"):
            out[-1] += "\n"

    # join with newlines and ensure trailing newline
    text = "\n".join(out)
    if not text.endswith("\n"):
        text += "\n"
    return text

def get_patches(project_path: str, test_name: str) -> List[DiffBlock]:
    # generate prompt
    debug_log_path = project_path + "/auto_debug.json"
    prompt = generate_prompt_as_string(debug_log_path, test_name)

    # query LLM
    model_response = run_completion(prompt)

    # parse patches from the response
    return parse_unified_diff(model_response)

@app.post("/debug")
def debug():
    data = request.get_json(force=True)

    if PROJECT_PATH is None:
        return jsonify({"error": "Server not configured with project path"}), 500

    patches = get_patches(PROJECT_PATH, data["testId"])
    patches_json = to_jsonable(patches)
    unified = build_unified_diff(patches_json)

    return jsonify({
        "project_root": PROJECT_PATH,
        "patches": patches_json,
        "unified_diff": unified
    }), 200

@app.get("/health")
def health():
    return "ok", 200

def main():
    global PROJECT_PATH

    if len(sys.argv) < 2:
        print("Usage: python server.py <project_path> [port]")
        sys.exit(1)

    PROJECT_PATH = sys.argv[1]
    port = int(os.environ.get("PORT", "5000"))
    app.run("127.0.0.1", port, debug=False)

if __name__ == "__main__":
    main()
