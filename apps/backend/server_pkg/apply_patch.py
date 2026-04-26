from __future__ import annotations
import re
from pathlib import Path
from typing import List, Tuple

Hunk = Tuple[int, int, int, int, List[str]]  # (a, b, c, d, raw change lines)
DiffBlock = Tuple[Path, List[Hunk]]

def parse_unified_diff(text: str) -> List[DiffBlock]:
    """
    Extract all unified‑diff blocks from *text*.

    Returns a list whose items are (file_path, [hunk, …]).
    Each *hunk* is (orig_start, orig_len, new_start, new_len, change_lines).
    """
    blocks: List[DiffBlock] = []
    i, lines = 0, text.splitlines()

    while i < len(lines):
        if not lines[i].startswith('--- '):
            i += 1
            continue

        old_path = lines[i][4:].strip()
        i += 1
        if i >= len(lines) or not lines[i].startswith('+++ '):
            raise ValueError(f'invalid diff: missing +++ after {old_path!r}')
        new_path = lines[i][4:].strip()
        file_path = Path(new_path)
        i += 1

        hunks: List[Hunk] = []
        while i < len(lines) and lines[i].startswith('@@'):
            m = re.match(r'@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@', lines[i])
            if not m:
                raise ValueError(f'bad hunk header: {lines[i]!r}')
            a, b, c, d = (int(m.group(k) or 1) for k in range(1, 5))
            i += 1

            change_lines: List[str] = []
            while i < len(lines) and not lines[i].startswith(('@@', '--- ')) and not lines[i] == "```":
                change_lines.append(lines[i])
                i += 1

            hunks.append((a, b, c, d, change_lines))

        blocks.append((file_path, hunks))

    return blocks
