from __future__ import annotations

from pathlib import Path


def read_text(path: Path) -> str:
    return (
        path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def render_numbered_range(source: str, start_line: int, end_line: int) -> str:
    if start_line < 1:
        start_line = 1
    if end_line < start_line:
        end_line = start_line

    lines = source.splitlines()
    if not lines:
        return ""

    start_idx = start_line - 1
    end_idx = min(len(lines), end_line)
    selected = lines[start_idx:end_idx]

    return "\n".join(
        f"{line_no}: {line}"
        for line_no, line in zip(range(start_line, start_line + len(selected)), selected)
    )


def render_source_context(source: str, line_number: int, context_size: int) -> str:
    if not source:
        return "<source unavailable>"
    lines = source.splitlines()
    if not lines:
        return "<source unavailable>"
    if line_number < 1:
        line_number = 1
    if line_number > len(lines):
        line_number = len(lines)
    start = max(1, line_number - context_size)
    end = min(len(lines), line_number + context_size)
    rendered = []
    for current in range(start, end + 1):
        marker = "->" if current == line_number else "  "
        rendered.append(f"{current} {marker} : {lines[current - 1]}")
    return "\n".join(rendered)
