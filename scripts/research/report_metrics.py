#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

VARIANTS = ("without_runtime", "with_runtime")


@dataclass
class VariantStats:
    total: int = 0
    successful: int = 0
    correct_file: int = 0
    correct_function: int = 0
    correct_line: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def absorb(self, variant_data: dict) -> None:
        self.total += 1
        outcome = variant_data.get("outcome", {})
        self.successful += int(bool(outcome.get("success", False)))
        loc = variant_data.get("localization_accuracy", {})
        self.correct_file += int(bool(loc.get("correct_file", False)))
        self.correct_function += int(bool(loc.get("correct_function", False)))
        self.correct_line += int(bool(loc.get("correct_line", False)))
        tok = variant_data.get("token_usage", {})
        self.input_tokens += int(tok.get("input_tokens", 0))
        self.output_tokens += int(tok.get("output_tokens", 0))

    def _pct(self, n: int) -> str:
        return f"{100 * n / self.total:.1f}%" if self.total else "n/a"

    def _avg(self, n: int) -> str:
        return f"{n / self.total:.0f}" if self.total else "n/a"

    def render(self, name: str) -> str:
        lines = [
            f"── {name} ──",
            f"  total:             {self.total}",
            f"  successful:        {self.successful}  ({self._pct(self.successful)})",
            f"  correct file:      {self.correct_file}  ({self._pct(self.correct_file)})",
            f"  correct function:  {self.correct_function}  ({self._pct(self.correct_function)})",
            f"  correct line:      {self.correct_line}  ({self._pct(self.correct_line)})",
            f"  avg input tokens:  {self._avg(self.input_tokens)}",
            f"  avg output tokens: {self._avg(self.output_tokens)}",
        ]
        return "\n".join(lines)


class RunReport:
    def __init__(self, run_dir: Path):
        self._run_dir = run_dir
        self._stats: dict[str, VariantStats] = {v: VariantStats() for v in VARIANTS}

    def process(self) -> None:
        artifacts_dir = self._run_dir / "artifacts"
        if not artifacts_dir.is_dir():
            raise SystemExit(f"artifacts/ not found in {self._run_dir}")
        reports = sorted(artifacts_dir.glob("*/comparison_report.json"))
        if not reports:
            raise SystemExit(f"No comparison_report.json files found in {artifacts_dir}")
        for path in reports:
            data = json.loads(path.read_text(encoding="utf-8"))
            for variant in VARIANTS:
                if variant in data:
                    self._stats[variant].absorb(data[variant])

    def print_summary(self) -> None:
        print(f"=== {self._run_dir.name} ===")
        for variant, stats in self._stats.items():
            print()
            print(stats.render(variant))


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize metrics from comparison_report.json files")
    parser.add_argument("run_dir", help="Path to benchmark run directory (containing artifacts/)")
    args = parser.parse_args()
    report = RunReport(Path(args.run_dir))
    report.process()
    report.print_summary()


if __name__ == "__main__":
    main()
