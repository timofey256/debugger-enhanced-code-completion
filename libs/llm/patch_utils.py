from __future__ import annotations

import re


def _find_diff_start(text: str) -> int | None:
    indexes: list[int] = []
    for pattern in (r"^diff --git ", r"^--- "):
        match = re.search(pattern, text, flags=re.MULTILINE)
        if match:
            indexes.append(match.start())
    return min(indexes) if indexes else None


def extract_unified_diff(response_text: str) -> str:
    if not response_text:
        return ""

    candidates: list[str] = []
    fenced_blocks = re.findall(r"```(?:diff)?\s*\n(.*?)```", response_text, flags=re.DOTALL)
    candidates.extend(fenced_blocks)
    candidates.append(response_text)

    for candidate in candidates:
        start_index = _find_diff_start(candidate)
        if start_index is None:
            continue
        patch = candidate[start_index:].strip()
        if patch:
            return patch + ("\n" if not patch.endswith("\n") else "")

    return ""
