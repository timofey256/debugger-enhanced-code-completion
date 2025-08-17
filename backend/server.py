from flask import Flask, request, jsonify
from main import get_patches
import os
from pathlib import Path

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

def build_unified_diff(project_root: str, patches_json):
    """Assemble a valid unified diff for all files/hunks."""
    out = []
    root = Path(project_root)

    for fp in patches_json:
        abs_path = Path(fp["path"])
        try:
            rel = abs_path.relative_to(root)
        except ValueError:
            # If given path isn't under project_root, just use basename
            rel = abs_path

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

@app.post("/debug")
def debug():
    project_path = "/home/tymofii/develop/debugger-enhanced-code-completion/example/jsonschema"
    data = request.get_json(force=True)

    patches = get_patches(project_path, data["testId"])
    patches_json = to_jsonable(patches)
    unified = build_unified_diff(project_path, patches_json)

    return jsonify({
        "project_root": project_path,
        "patches": patches_json,
        "unified_diff": unified
    }), 200

@app.get("/health")
def health():
    return "ok", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5123"))
    app.run("127.0.0.1", port, debug=False)

