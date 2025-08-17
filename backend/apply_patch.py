from __future__ import annotations
import re
from pathlib import Path
from typing import List, Tuple
import sys

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
            while i < len(lines) and not lines[i].startswith(('@@', '--- ')):
                change_lines.append(lines[i])
                i += 1

            hunks.append((a, b, c, d, change_lines))

        blocks.append((file_path, hunks))

    return blocks


def apply_diff(blocks: List[DiffBlock]) -> None:
    """
    Mutate each file on disk according to *blocks* (as parsed above).
    """
    for file_path, hunks in blocks:
        original_lines = Path(file_path).read_text().splitlines()

        # apply bottom‑up so indexes don't shift
        for a, b, _, _, change_lines in reversed(hunks):
            # 1‑based → 0‑based
            idx = a - 1 # TODO: Why is it 2??? 1 doesn't work. some indexing issue before 
            del original_lines[idx: idx + b] # remove old lines

            additions = [
                ln[1:] # strip '+' / ' '
                for ln in change_lines
                if ln.startswith(('+', ' '))
            ]
            original_lines[idx:idx] = additions      # insert new/context

        Path(file_path).write_text('\n'.join(original_lines) + '\n')


def patch_code(prompt_text: str) -> None:
    """
    One‑liner convenience: call this with the full LLM prompt.
    """
    apply_diff(parse_unified_diff(prompt_text))

def patch_from_file(path: str) -> None:
    """
    One‑liner convenience: call this with the full LLM prompt.
    """
    with open(path, "r") as f:
        patch_code(f.read())

if __name__ == "__main__":
    response_path = sys.argv[1] 
    patch_from_file(response_path)
