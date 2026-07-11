#!/usr/bin/env python
"""
Validate the generated traces against source code

Run from the repository root:

python research/swebench/sft/validate_sft_dataset.py \
    --run-dir output/benchmark-runs/<run_id> \
    --dataset output/sft/<file>.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")


class DatasetValidator:
    def __init__(self, run_dir: Path):
        self._run_dir = run_dir
        self._gold_cache: dict[str, dict[str, list[tuple[int, int]]]] = {}

    def validate(self, dataset_path: Path) -> dict[str, Any]:
        rows = [json.loads(line) for line in dataset_path.open()]
        report: dict[str, Any] = {
            "rows": len(rows),
            "errors": 0,
            "empty_outputs": 0,
            "missing_patch": 0,
            "coverage_full": 0,
            "coverage_partial": 0,
            "grounded": 0,
            "by_framework": Counter(),
            "by_source": Counter(),
            "shapes": Counter(),
            "instances": Counter(),
            "failures": [],
        }
        for row in rows:
            self._check_row(row, report)
        report["unique_instances"] = len(report["instances"])
        report["duplicate_variants"] = sum(c for c in report["instances"].values() if c > 1)
        return report

    def _check_row(self, row: dict, report: dict) -> None:
        iid = row["instance_id"]
        report["instances"][iid] += 1
        report["by_framework"][iid.split("__")[0]] += 1
        report["by_source"][row.get("meta", {}).get("source", "?")] += 1
        if row.get("meta", {}).get("runtime_grounded"):
            report["grounded"] += 1

        opened: dict[str, list[tuple[int, int]]] = {}
        seq: list[str] = []
        has_patch = False
        for msg in row["messages"]:
            if msg["role"] == "assistant":
                fn = msg["tool_calls"][0]["function"]
                seq.append(fn["name"])
                if fn["name"] == "apply_patch":
                    args = json.loads(fn["arguments"])
                    has_patch = bool(args.get("patch", "").strip())
                elif fn["name"] == "open_file":
                    args = json.loads(fn["arguments"])
                    path = args["path"].replace("/testbed/", "")
                    opened.setdefault(path, []).append((args["start_line"], args["end_line"]))
            elif msg["role"] == "tool":
                content = msg["content"]
                if "status=error" in content or "status=unimplemented" in content:
                    report["errors"] += 1
                    report["failures"].append((iid, "error_output", msg.get("name")))
                if msg.get("name") != "apply_patch":
                    body = content.split("output:\n", 1)[-1].rsplit("</tool_result>", 1)[0].strip()
                    if not body:
                        report["empty_outputs"] += 1
                        report["failures"].append((iid, "empty_output", msg.get("name")))

        report["shapes"][self._shape(seq)] += 1
        if not has_patch:
            report["missing_patch"] += 1
            report["failures"].append((iid, "missing_patch", None))
        self._check_coverage(iid, opened, report)

    def _check_coverage(self, iid: str, opened: dict, report: dict) -> None:
        gold = self._gold(iid)
        if not gold:
            return
        files_hit = 0
        for pf, ranges in gold.items():
            hit = any(
                os_ <= ge and gs <= oe
                for (gs, ge) in ranges
                for (os_, oe) in opened.get(pf, [])
            )
            files_hit += 1 if hit else 0
        if files_hit == len(gold):
            report["coverage_full"] += 1
        else:
            report["coverage_partial"] += 1
            report["failures"].append((iid, "coverage_partial", f"{files_hit}/{len(gold)}"))

    def _gold(self, iid: str) -> dict[str, list[tuple[int, int]]]:
        if iid in self._gold_cache:
            return self._gold_cache[iid]
        path = self._run_dir / "artifacts" / iid / "reference_patch.diff"
        ranges: dict[str, list[tuple[int, int]]] = {}
        if path.is_file():
            current = None
            for line in path.read_text(errors="replace").splitlines():
                if line.startswith("+++ "):
                    current = line[4:].strip()
                    for prefix in ("a/", "b/"):
                        if current.startswith(prefix):
                            current = current[len(prefix):]
                m = HUNK.match(line)
                if m and current:
                    start = int(m.group(1))
                    length = int(m.group(2)) if m.group(2) else 1
                    ranges.setdefault(current, []).append((start, start + max(length, 1)))
        self._gold_cache[iid] = ranges
        return ranges

    @staticmethod
    def _shape(seq: list[str]) -> str:
        short = {
            "get_test_error": "err",
            "get_execution_trace": "exec",
            "get_frames": "fr",
            "get_granular_frames": "gfr",
            "open_file": "open",
            "search_symbol": "sym",
            "print_project_tree": "tree",
            "apply_patch": "patch",
        }
        return "→".join(short.get(s, s) for s in seq)


def _parse_args():
    parser = argparse.ArgumentParser(description="Validate an SFT trajectory dataset.")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--show-failures", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = DatasetValidator(args.run_dir).validate(args.dataset)
    if args.show_failures and report["failures"]:
        print(f"--- failures (first {args.show_failures}) ---")
        for item in report["failures"][: args.show_failures]:
            print(f"  {item}")


if __name__ == "__main__":
    main()
