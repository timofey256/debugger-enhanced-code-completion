#!/usr/bin/env python3

from __future__ import annotations
import sys, json, textwrap
from pathlib import Path

_TEMPLATE = textwrap.dedent("""\
    You are acting as a coding assistant who produces **atomic code patches**.

    Goal → **complete / fix** the code so the program runs correctly.

    ## Exception type: {exception_type}
    ## Exception message: {exception_msg}

    ## Runtime trace
    {runtime_trace}

    ## What you must do
    1. **Diagnose** the issue using the trace frames and source context provided.
    2. Produce **a unified diff patch** (one per file) that fixes the issue.
       - Use the unified diff format:
         - `--- path/to/file.py` for the original file
         - `+++ path/to/file.py` for the new version
         - Each hunk begins with `@@ -a,b +c,d @@`
         - Lines to delete start with `-`, lines to add start with `+`
         - Include at most 3 lines of **unchanged context** above and below (i.e., use `-U3`)
       - **Do not** include commentary or prose—output only the diff.
    3. If multiple files need a change, output multiple diff blocks.
    4. **Carefully set the starting line number `a` in the hunk header** so it matches the first unchanged or deleted line from the original file.
    5. The diff **must exactly align** with the source context shown in the trace blocks. Do not shift it up or down.
    6. Make sure to include the whole file path, not just the file name.
    7. Make sure you copy all the comments from the source code.

    ### Example - correct diff with aligned header and context
    Original context:
      40 : def scale(x):
      41 :     if x is None:
      42 :         return 0
      43 :     return x * 2

    You want to modify lines 41-43. Then your diff must look like this:

    ```diff
    --- src/utils/math.py
    +++ src/utils/math.py
    @@ -41,3 +41,4 @@
         if x is None:
             return 0
         return x * 2
    +    # New logic here
    ```

    ⚠️ Common mistakes to avoid:
    - Incorrect start line in the hunk (off by 1 or 2)
    - Including too many context lines and shifting the diff
    - Forgetting to match the source indentation

    Nothing else—just the diff.
    """)

def get_ctx_around_line(filename: str, line_nmbr: int, context_size: int) -> str:
    assert context_size > 0, "context_size must be non-negative"
    assert line_nmbr >= 1, "line_nmbr must be >= 1"

    lines = Path(filename).read_text(encoding="utf-8", errors="replace").splitlines()
    total = len(lines)

    start = max(1, line_nmbr - context_size)
    end   = min(total, line_nmbr + context_size)

    snippets = lines[start - 1 : end]
    return "\n".join(f"{line_nmbr-context_size+n} {("->" if context_size==n else "  ")} : {snippet}" for n, snippet in enumerate(snippets))

def serialize_trace(obj: dict) -> str:
    return "```trace\n" + json.dumps(obj, indent=2) + "\n```"

def serialize_frames(frames: list[dict], context_size: int = 10) -> str:
    FRAME_TEMPLATE = textwrap.dedent("""\
        File: {filename}
        Function name: {function_name}
        Line: {line}
        Context:
        {context}
        Locals: {locals}
        """)

    serialized_frame_blocks = [
        FRAME_TEMPLATE.format(
            filename=frame["file"],
            function_name=frame["func"],
            line=frame["line"],
            context=get_ctx_around_line(frame["file"], frame["line"], context_size),
            locals=frame["locals"]
            )
        for frame in frames
    ]

    return "\n".join([f"Block {i}:\n{block}" for i, block in enumerate(serialized_frame_blocks)])

def build_prompt(trace: dict) -> str:
    frames = serialize_frames(trace["frames"])
    return _TEMPLATE.format(exception_type=trace["exc_type"], exception_msg=trace["message"], runtime_trace=frames)

def read_json(source: str | Path | None) -> list[dict]:
    raw = sys.stdin.read() if source in (None, "-", "") else Path(source).read_text()
    return json.loads(raw)

def generate_prompt_as_string(traces_path) -> None:
    all_traces = read_json(traces_path)
    trace = all_traces[0] 
    prompt = build_prompt(trace)
    return prompt

def main(argv: list[str] = sys.argv[1:]) -> None:
    src = argv[0] if argv else None
    #src = "/home/tymofii/school/isp/debugger-enhanced-code-completion/example/jsonschema/auto_debug.json"
    all_traces = read_json(src)
    trace = all_traces[0] 
    prompt = build_prompt(trace)
    with open("/home/tymofii/school/isp/debugger-enhanced-code-completion/prompt_log/prompt.txt", "w") as f:
        f.write(prompt)

if __name__ == "__main__":
    main()