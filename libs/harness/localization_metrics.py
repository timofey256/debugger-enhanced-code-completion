from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class PatchHunk:
    file: str
    function_name: str
    changed_lines: set


_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)")


def parse_patch_hunks(patch_text: str) -> List[PatchHunk]:
    hunks: List[PatchHunk] = []
    current_file = ""
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split(" b/", 1)
            current_file = parts[1] if len(parts) == 2 else ""
        elif line.startswith("+++ "):
            path = line[4:]
            if path.startswith("b/"):
                path = path[2:]
            if path != "/dev/null" and not current_file:
                current_file = path
        m = _HUNK_HEADER_RE.match(line)
        if m and current_file:
            old_start = int(m.group(1))
            old_count = int(m.group(2)) if m.group(2) is not None else 1
            new_start = int(m.group(3))
            new_count = int(m.group(4)) if m.group(4) is not None else 1
            func_name = m.group(5).strip()
            changed = set(range(old_start, old_start + old_count)) | set(range(new_start, new_start + new_count))
            hunks.append(PatchHunk(file=current_file, function_name=func_name, changed_lines=changed))
    return hunks


def compute_localization_accuracy(generated_patch: str, reference_patch: str) -> Dict[str, bool]:
    empty: Dict[str, bool] = {"correct_file": False, "correct_function": False, "correct_line": False}
    if not generated_patch.strip() or not reference_patch.strip():
        return empty
    gen_hunks = parse_patch_hunks(generated_patch)
    ref_hunks = parse_patch_hunks(reference_patch)
    if not gen_hunks or not ref_hunks:
        return empty
    ref_files = {h.file for h in ref_hunks}
    ref_funcs = {(h.file, h.function_name) for h in ref_hunks if h.function_name}
    ref_file_lines: Dict[str, set] = {}
    for h in ref_hunks:
        ref_file_lines.setdefault(h.file, set()).update(h.changed_lines)
    correct_file = any(h.file in ref_files for h in gen_hunks)
    correct_function = any(
        h.function_name and (h.file, h.function_name) in ref_funcs
        for h in gen_hunks
    )
    correct_line = any(
        bool(h.changed_lines & ref_file_lines.get(h.file, set()))
        for h in gen_hunks
    )
    return {"correct_file": correct_file, "correct_function": correct_function, "correct_line": correct_line}
