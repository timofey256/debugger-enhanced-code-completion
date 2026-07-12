from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

_HUNK_HEADER = re.compile(r"^@@+\s*-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s*@@")


def _strip_path(raw: str) -> str:
    value = raw.strip()
    if "\t" in value:
        value = value.split("\t", 1)[0].strip()
    if value in ("a/dev/null", "b/dev/null", "/dev/null"):
        return "/dev/null"
    if value.startswith(("a/", "b/")):
        value = value[2:]
    if value.startswith("/testbed/"):
        value = value[len("/testbed/"):]
    return value


@dataclass
class Hunk:
    """One diff hunk: the old-side start line and the raw body lines."""

    old_start: int
    body: List[str] = field(default_factory=list)

    def old_block(self) -> List[str]:
        out: List[str] = []
        for line in self.body:
            if line == "":
                out.append("")
            elif line[0] in (" ", "-"):
                out.append(line[1:])
        return out

    def new_block(self) -> List[str]:
        out: List[str] = []
        for line in self.body:
            if line == "":
                out.append("")
            elif line[0] in (" ", "+"):
                out.append(line[1:])
        return out


@dataclass
class FilePatch:
    """All hunks of one file in a diff, plus new/delete flags."""

    path: str
    hunks: List[Hunk] = field(default_factory=list)
    is_new: bool = False
    is_delete: bool = False


class UnifiedDiffParser:
    """Parses unified diff text into `FilePatch` objects, tolerating minor format defects."""

    def parse(self, text: str) -> List[FilePatch]:
        files: List[FilePatch] = []
        current: Optional[FilePatch] = None
        hunk: Optional[Hunk] = None
        pending_old: Optional[str] = None

        for line in text.splitlines():
            if line.startswith("diff --git"):
                current = None
                hunk = None
                pending_old = None
            elif line.startswith("--- "):
                pending_old = _strip_path(line[4:])
                hunk = None
            elif line.startswith("+++ "):
                new_path = _strip_path(line[4:])
                path = new_path if new_path != "/dev/null" else (pending_old or "")
                current = FilePatch(
                    path=path,
                    is_new=pending_old == "/dev/null",
                    is_delete=new_path == "/dev/null",
                )
                files.append(current)
                hunk = None
            elif line.startswith("@@"):
                match = _HUNK_HEADER.match(line)
                if match and current is not None:
                    hunk = Hunk(old_start=int(match.group(1)))
                    current.hunks.append(hunk)
                else:
                    hunk = None
            elif hunk is not None:
                if line.startswith("\\"):
                    continue
                if line == "" or line[0] in (" ", "+", "-"):
                    hunk.body.append(line)
                else:
                    hunk = None

        return [f for f in files if f.hunks or f.is_new or f.is_delete]


class HunkLocator:
    """Finds where a hunk's old block sits in the file, with exact then fuzzy matching."""

    def __init__(self, fuzz: float = 0.75):
        self._fuzz = fuzz

    def locate(self, haystack: List[str], block: List[str], hint: int) -> Optional[int]:
        n, m = len(haystack), len(block)
        if m == 0:
            return max(0, min(hint, n))
        if m > n:
            return self._fuzzy(haystack, block)

        for normalize in (lambda s: s, str.rstrip, str.strip):
            target = [normalize(x) for x in block]
            matches = [
                i
                for i in range(n - m + 1)
                if [normalize(y) for y in haystack[i:i + m]] == target
            ]
            if matches:
                return min(matches, key=lambda c: abs(c - hint))

        return self._fuzzy(haystack, block)

    def _fuzzy(self, haystack: List[str], block: List[str]) -> Optional[int]:
        m = len(block)
        n = len(haystack)
        target = [x.strip() for x in block]
        best_index: Optional[int] = None
        best_score = 0.0
        for i in range(0, max(1, n - m + 1)):
            window = [y.strip() for y in haystack[i:i + m]]
            score = difflib.SequenceMatcher(None, window, target).ratio()
            if score > best_score:
                best_score = score
                best_index = i
        if best_index is not None and best_score >= self._fuzz:
            return best_index
        return None


class PatchReconstructor:
    """Rebuilds a malformed model patch into a clean, appliable diff against the real file contents."""

    def __init__(self, project_root: Path, fuzz: float = 0.75):
        self._root = Path(project_root)
        self._locator = HunkLocator(fuzz=fuzz)
        self._parser = UnifiedDiffParser()

    def reconstruct(self, patch_text: str) -> Optional[str]:
        if not patch_text.strip():
            return None
        files = self._parser.parse(patch_text)
        if not files:
            return None

        diffs: List[str] = []
        for file_patch in files:
            rendered = self._reconstruct_file(file_patch)
            if rendered is None:
                return None
            if rendered:
                diffs.append(rendered)

        if not diffs:
            return None
        return "".join(diffs)

    def _reconstruct_file(self, file_patch: FilePatch) -> Optional[str]:
        if file_patch.is_delete:
            return None

        original, had_newline = self._read_original(file_patch)
        if original is None:
            return None

        updated = self._apply_hunks(original, file_patch.hunks)
        if updated is None:
            return None
        if updated == original:
            return ""

        return self._render_diff(file_patch.path, original, updated, had_newline)

    def _read_original(self, file_patch: FilePatch) -> tuple[Optional[List[str]], bool]:
        if file_patch.is_new:
            return [], True
        target = self._root / file_patch.path
        if not target.is_file():
            return None, True
        text = target.read_text(encoding="utf-8", errors="replace")
        had_newline = text.endswith("\n")
        lines = text.split("\n")
        if had_newline and lines and lines[-1] == "":
            lines.pop()
        return lines, had_newline

    def _apply_hunks(self, original: List[str], hunks: List[Hunk]) -> Optional[List[str]]:
        result = list(original)
        offset = 0
        for hunk in hunks:
            old_block = hunk.old_block()
            new_block = hunk.new_block()
            hint = max(0, hunk.old_start - 1 + offset)
            index = self._locator.locate(result, old_block, hint)
            if index is None:
                return None
            end = index + len(old_block)
            result[index:end] = new_block
            offset += len(new_block) - len(old_block)
        return result

    def _render_diff(
        self, path: str, original: List[str], updated: List[str], had_newline: bool
    ) -> str:
        from_file = f"a/{path}"
        to_file = f"b/{path}"
        diff = difflib.unified_diff(
            original, updated, fromfile=from_file, tofile=to_file, lineterm="", n=3
        )
        lines = list(diff)
        if not lines:
            return ""
        header = f"diff --git {from_file} {to_file}"
        return "\n".join([header] + lines) + "\n"
