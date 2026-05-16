#!/usr/bin/env python3

from __future__ import annotations
import sys, json
from pathlib import Path

from prompts import PromptBuilder, load_prompt
from libs.frames import Frame, default_traceback_pipeline

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
    frame_template = load_prompt("debugger/frame_template.txt")

    serialized_frame_blocks = [
        frame_template.format(
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
    raw_frames = trace.get("frames", []) or []
    pipelined = [
        f.to_json()
        for f in default_traceback_pipeline().run(
            Frame.from_json(d) for d in raw_frames
        )
    ]
    frames = serialize_frames(pipelined)
    exception_body = (
        f"Type: {trace['exc_type']}\n"
        f"Message: {trace['message']}"
    )
    return (
        PromptBuilder()
        .add_section("intro", load_prompt("debugger/intro.txt").rstrip("\n"))
        .add_section("exception", exception_body)
        .add_section("runtime_trace", frames)
        .add_section("instructions", load_prompt("debugger/instructions.txt").rstrip("\n"))
        .add_section("patch_format", load_prompt("swebench/strict_patch_requirements.txt").rstrip("\n"))
        .build()
    )

def read_json(source: str | Path | None) -> list[dict]:
    raw = sys.stdin.read() if source in (None, "-", "") else Path(source).read_text()
    return json.loads(raw)

def generate_prompt_as_string(project_path: str, test_name: str) -> str | None:
    all_traces = read_json(project_path)
    trace =  next((t for t in all_traces if t["nodeid"] == test_name), None)
    if trace:
        prompt = build_prompt(trace)
        return prompt
    else:
        print(f"Error: failed to find a test matching nodeid = {test_name}")
        return None

def main(argv: list[str] = sys.argv[1:]) -> None:
    src = argv[0] if argv else None
    all_traces = read_json(src)
    trace = all_traces[0]
    prompt = build_prompt(trace)
    out_path = Path(argv[1]) if len(argv) > 1 else Path("output/traces/prompt.txt")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write(prompt)

if __name__ == "__main__":
    main()
