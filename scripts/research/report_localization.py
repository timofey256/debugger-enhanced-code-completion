#!/usr/bin/env python3
"""Size-aware localization metrics over comparison_report.json files.

Same CLI shape as report_metrics.py: takes a benchmark run directory that
contains an artifacts/ subdirectory and prints per-variant statistics.

Metrics reported per variant:
  - file P/R/F1     over the set of files touched by the patch
  - function P/R/F1 over (file, function) pairs derived from hunk trailers
                    (with line-range propagation when the predicted hunk
                    has no trailer)
  - line P/R/F1     over (file, pre-image line) pairs, restricted to lines
                    that actually carry a + or - prefix (context lines are
                    excluded). Pure insertions are anchored to the
                    pre-image line immediately before the insertion point.
  - hunk IoU at threshold 0.5, with greedy maximum-IoU matching per file
  - average patch size in edited lines

Each instance contributes one F1 to the average (macro averaging over
instances). Instances whose gold patch is empty are excluded from the
localization averages.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

VARIANTS = ("without_runtime", "with_runtime")

_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")
_FILE_NEW_RE = re.compile(r"^\+\+\+ (?:b/)?(.+)$")
_HUNK_HEADER_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$"
)
_FUNC_RE = re.compile(r"\b(?:def|class)\s+([A-Za-z_]\w*)")

PROPAGATE_WINDOW = 30


@dataclass
class Hunk:
    file: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    trailer: str
    body: list[str] = field(default_factory=list)
    function_name: Optional[str] = None
    changed_lines: set = field(default_factory=set)
    edits: list = field(default_factory=list)  # list of (anchor, op, normalized content)

    def pre_image_range(self) -> tuple[int, int]:
        if self.old_count == 0:
            return (self.old_start, self.old_start)
        return (self.old_start, self.old_start + self.old_count - 1)

    def pre_image_span(self) -> set:
        lo, hi = self.pre_image_range()
        return set(range(lo, hi + 1))


def _compute_changes(body: list[str], old_start: int) -> tuple[set, list]:
    """Walk hunk body once, returning (changed_line_set, edit_sequence).

    edit_sequence is a list of (anchor, op, normalized_content) tuples in
    hunk order. Content normalization strips trailing whitespace, per the
    Patch change set definition in evaluation.tex.
    """
    changed: set = set()
    edits: list = []
    pre_line = old_start
    last_pre = old_start - 1
    for line in body:
        if not line:
            last_pre = pre_line
            pre_line += 1
            continue
        head = line[0]
        if head == " ":
            last_pre = pre_line
            pre_line += 1
        elif head == "-":
            changed.add(pre_line)
            edits.append((pre_line, "-", line[1:].rstrip()))
            last_pre = pre_line
            pre_line += 1
        elif head == "+":
            anchor = last_pre if last_pre >= old_start else old_start
            changed.add(anchor)
            edits.append((anchor, "+", line[1:].rstrip()))
        else:
            last_pre = pre_line
            pre_line += 1
    return changed, edits


def parse_patch(patch_text: str) -> list[Hunk]:
    hunks: list[Hunk] = []
    if not patch_text:
        return hunks
    current_file = ""
    current_hunk: Optional[Hunk] = None

    def finalize(h: Hunk) -> None:
        h.changed_lines, h.edits = _compute_changes(h.body, h.old_start)
        if h.trailer:
            m = _FUNC_RE.search(h.trailer)
            if m:
                h.function_name = m.group(1)

    for line in patch_text.splitlines():
        m = _DIFF_GIT_RE.match(line)
        if m:
            if current_hunk is not None:
                finalize(current_hunk)
                hunks.append(current_hunk)
                current_hunk = None
            current_file = m.group(2)
            continue
        if line.startswith("--- "):
            continue
        m = _FILE_NEW_RE.match(line)
        if m:
            path = m.group(1)
            if path != "/dev/null":
                current_file = path
            continue
        m = _HUNK_HEADER_RE.match(line)
        if m:
            if current_hunk is not None:
                finalize(current_hunk)
                hunks.append(current_hunk)
            if not current_file:
                current_hunk = None
                continue
            old_start = int(m.group(1))
            old_count = int(m.group(2)) if m.group(2) is not None else 1
            new_start = int(m.group(3))
            new_count = int(m.group(4)) if m.group(4) is not None else 1
            current_hunk = Hunk(
                file=current_file,
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                trailer=m.group(5).strip(),
            )
            continue
        if current_hunk is not None:
            current_hunk.body.append(line)

    if current_hunk is not None:
        finalize(current_hunk)
        hunks.append(current_hunk)
    return hunks


def _propagate_function(pred_hunks: list[Hunk], gold_hunks: list[Hunk]) -> None:
    """Predicted hunks without a trailer inherit the function name of the
    closest gold hunk in the same file whose pre-image range overlaps or is
    within PROPAGATE_WINDOW lines. Best-effort, used only for the function
    metric so that minimal diffs without function context still score."""
    by_file: dict[str, list[Hunk]] = {}
    for gh in gold_hunks:
        if gh.function_name:
            by_file.setdefault(gh.file, []).append(gh)
    for ph in pred_hunks:
        if ph.function_name:
            continue
        candidates = by_file.get(ph.file, [])
        if not candidates:
            continue
        p_lo, p_hi = ph.pre_image_range()
        best: Optional[Hunk] = None
        best_dist = 1_000_000
        for gh in candidates:
            g_lo, g_hi = gh.pre_image_range()
            if p_hi >= g_lo and p_lo <= g_hi:
                dist = 0
            else:
                dist = min(abs(p_lo - g_hi), abs(g_lo - p_hi))
            if dist < best_dist:
                best_dist = dist
                best = gh
        if best is not None and best_dist <= PROPAGATE_WINDOW:
            ph.function_name = best.function_name


def _set_prf(pred: set, gold: set) -> tuple[float, float, float]:
    if not gold and not pred:
        return (1.0, 1.0, 1.0)
    if not pred or not gold:
        return (0.0, 0.0, 0.0)
    tp = len(pred & gold)
    p = tp / len(pred)
    r = tp / len(gold)
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return (p, r, f1)


def _iou(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def hunk_iou_match(
    pred_hunks: list[Hunk], gold_hunks: list[Hunk], threshold: float = 0.5
) -> tuple[int, int, int]:
    pairs: list[tuple[float, int, int]] = []
    for i, ph in enumerate(pred_hunks):
        p_span = ph.pre_image_span()
        for j, gh in enumerate(gold_hunks):
            if ph.file != gh.file:
                continue
            iou = _iou(p_span, gh.pre_image_span())
            if iou >= threshold:
                pairs.append((iou, i, j))
    pairs.sort(reverse=True)
    used_pred: set = set()
    used_gold: set = set()
    matched = 0
    for _iou_val, i, j in pairs:
        if i in used_pred or j in used_gold:
            continue
        used_pred.add(i)
        used_gold.add(j)
        matched += 1
    return (matched, len(pred_hunks), len(gold_hunks))


def _levenshtein(a: str, b: str) -> int:
    """Character-level Levenshtein distance (Wagner-Fischer, two-row DP)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a
    n = len(b)
    prev = list(range(n + 1))
    curr = [0] * (n + 1)
    for i, ca in enumerate(a, 1):
        curr[0] = i
        for j in range(1, n + 1):
            cost = 0 if ca == b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev, curr = curr, prev
    return prev[n]


def _patch_c_string(hunks: list[Hunk]) -> str:
    """Build c(P): concatenation of op + normalized content over edits sorted
    by (file, anchor, op, in-hunk position). Hunk index is appended as a
    final tie-breaker to ensure determinism across cross-hunk duplicates."""
    items: list = []
    for h_idx, h in enumerate(hunks):
        for inner_idx, (anchor, op, content) in enumerate(h.edits):
            items.append((h.file, anchor, op, inner_idx, h_idx, content))
    items.sort()
    return "".join(item[2] + item[5] for item in items)


def _patch_edit_count(patch_text: str) -> int:
    count = 0
    for line in patch_text.splitlines():
        if not line:
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+") or line.startswith("-"):
            count += 1
    return count


@dataclass
class VariantStats:
    total: int = 0
    resolved: int = 0
    applied: int = 0
    skipped_empty_gold: int = 0

    file_p: float = 0.0
    file_r: float = 0.0
    file_f1: float = 0.0
    func_p: float = 0.0
    func_r: float = 0.0
    func_f1: float = 0.0
    line_p: float = 0.0
    line_r: float = 0.0
    line_f1: float = 0.0

    hunk_tp: int = 0
    hunk_pred: int = 0
    hunk_gold: int = 0

    patch_size_sum: int = 0
    patch_size_count: int = 0

    levsim_sum: float = 0.0

    def absorb(self, variant_data: dict, gold_patch: str) -> None:
        self.total += 1
        outcome = variant_data.get("outcome", {})
        resolved = outcome.get("resolved")
        if resolved is None:
            resolved = outcome.get("success", False)
        self.resolved += int(bool(resolved))
        status = outcome.get("status")
        self.applied += int(status not in ("apply_failed", "not_run", None))

        pred_patch = variant_data.get("generated_patch", "") or ""
        if pred_patch.strip():
            self.patch_size_sum += _patch_edit_count(pred_patch)
            self.patch_size_count += 1

        gold_hunks = parse_patch(gold_patch)
        pred_hunks = parse_patch(pred_patch)

        # Normalized Levenshtein similarity is defined over all instances,
        # so we compute it before any empty-gold skip.
        c_pred = _patch_c_string(pred_hunks)
        c_gold = _patch_c_string(gold_hunks)
        if not c_pred and not c_gold:
            self.levsim_sum += 1.0
        elif not c_pred or not c_gold:
            pass  # d_i = 0
        else:
            denom = max(len(c_pred), len(c_gold))
            self.levsim_sum += 1.0 - _levenshtein(c_pred, c_gold) / denom

        if not gold_hunks:
            self.skipped_empty_gold += 1
            return

        _propagate_function(pred_hunks, gold_hunks)

        pred_files = {h.file for h in pred_hunks}
        gold_files = {h.file for h in gold_hunks}
        pred_funcs = {(h.file, h.function_name) for h in pred_hunks if h.function_name}
        gold_funcs = {(h.file, h.function_name) for h in gold_hunks if h.function_name}
        pred_lines = {(h.file, ln) for h in pred_hunks for ln in h.changed_lines}
        gold_lines = {(h.file, ln) for h in gold_hunks for ln in h.changed_lines}

        p, r, f = _set_prf(pred_files, gold_files)
        self.file_p += p
        self.file_r += r
        self.file_f1 += f
        p, r, f = _set_prf(pred_funcs, gold_funcs)
        self.func_p += p
        self.func_r += r
        self.func_f1 += f
        p, r, f = _set_prf(pred_lines, gold_lines)
        self.line_p += p
        self.line_r += r
        self.line_f1 += f

        tp, np_h, ng_h = hunk_iou_match(pred_hunks, gold_hunks, 0.5)
        self.hunk_tp += tp
        self.hunk_pred += np_h
        self.hunk_gold += ng_h

    def _avg(self, total: float) -> str:
        n = self.total - self.skipped_empty_gold
        return f"{total / n:.3f}" if n else "n/a"

    def _pct(self, n: int) -> str:
        return f"{100 * n / self.total:.1f}%" if self.total else "n/a"

    def render(self, name: str) -> str:
        n_eff = self.total - self.skipped_empty_gold
        if self.hunk_pred and self.hunk_gold:
            hp = self.hunk_tp / self.hunk_pred
            hr = self.hunk_tp / self.hunk_gold
            hf = 2 * hp * hr / (hp + hr) if (hp + hr) else 0.0
            hunk_line = f"{hp:.3f} / {hr:.3f} / {hf:.3f}"
        else:
            hunk_line = "n/a"
        patch_avg = (
            f"{self.patch_size_sum / self.patch_size_count:.2f}"
            if self.patch_size_count
            else "n/a"
        )
        levsim = (
            f"{self.levsim_sum / self.total:.3f}" if self.total else "n/a"
        )
        lines = [
            f"── {name} ──",
            f"  total:                  {self.total}  (localization n: {n_eff})",
            f"  resolved:               {self.resolved}  ({self._pct(self.resolved)})",
            f"  patch applied:          {self.applied}  ({self._pct(self.applied)})",
            f"  file   P/R/F1:          {self._avg(self.file_p)} / {self._avg(self.file_r)} / {self._avg(self.file_f1)}",
            f"  func   P/R/F1:          {self._avg(self.func_p)} / {self._avg(self.func_r)} / {self._avg(self.func_f1)}",
            f"  line   P/R/F1:          {self._avg(self.line_p)} / {self._avg(self.line_r)} / {self._avg(self.line_f1)}",
            f"  hunk IoU>=0.5 P/R/F1:   {hunk_line}",
            f"  LevSim:                 {levsim}",
            f"  avg patch +/- lines:    {patch_avg}",
        ]
        if self.skipped_empty_gold:
            lines.append(
                f"  skipped (empty gold):   {self.skipped_empty_gold}"
            )
        return "\n".join(lines)


class RunReport:
    def __init__(self, run_dir: Path):
        self._run_dir = run_dir
        self._stats: dict[str, VariantStats] = {v: VariantStats() for v in VARIANTS}

    def _load_gold(self, report_path: Path, data: dict) -> str:
        patches = data.get("patches") or {}
        for key in ("reference_swebench", "reference"):
            value = patches.get(key)
            if isinstance(value, str) and value.strip():
                return value
        top_level = data.get("reference_patch")
        if isinstance(top_level, str) and top_level.strip():
            return top_level
        sibling = report_path.parent / "reference_patch.diff"
        if sibling.is_file():
            return sibling.read_text(encoding="utf-8")
        return ""

    def process(self) -> None:
        artifacts_dir = self._run_dir / "artifacts"
        if not artifacts_dir.is_dir():
            raise SystemExit(f"artifacts/ not found in {self._run_dir}")
        reports = sorted(artifacts_dir.glob("*/comparison_report.json"))
        if not reports:
            raise SystemExit(
                f"No comparison_report.json files found in {artifacts_dir}"
            )
        for path in reports:
            data = json.loads(path.read_text(encoding="utf-8"))
            gold = self._load_gold(path, data)
            for variant in VARIANTS:
                if variant in data:
                    self._stats[variant].absorb(data[variant], gold)

    def print_summary(self) -> None:
        print(f"=== {self._run_dir.name} ===")
        for variant, stats in self._stats.items():
            print()
            print(stats.render(variant))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Size-aware localization metrics (file/func/line precision, "
            "recall, F1 plus hunk IoU) from comparison_report.json files"
        )
    )
    parser.add_argument(
        "run_dir",
        help="Path to benchmark run directory (containing artifacts/)",
    )
    args = parser.parse_args()
    report = RunReport(Path(args.run_dir))
    report.process()
    report.print_summary()


if __name__ == "__main__":
    main()
