#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

VARIANTS = ("without_runtime", "with_runtime")


@dataclass
class VariantUsage:
    instances: int = 0
    totals: Counter = field(default_factory=Counter)

    def absorb(self, variant_data: dict) -> None:
        tool_counts = variant_data.get("tool_call_counts")
        if tool_counts is None:
            return
        self.instances += 1
        for tool, n in tool_counts.items():
            self.totals[tool] += int(n)

    def _avg(self, n: int) -> float:
        return n / self.instances if self.instances else 0.0

    def render(self, name: str) -> str:
        lines = [f"-- {name} (instances: {self.instances}) --"]
        for tool in sorted(self.totals):
            total = self.totals[tool]
            lines.append(f"  {tool:<20} total={total:<6} avg={self._avg(total):.3f}")
        grand = sum(self.totals.values())
        lines.append(f"  {'TOTAL':<20} total={grand:<6} avg={self._avg(grand):.3f}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "instances": self.instances,
            "tools": {
                tool: {"total": total, "avg_per_instance": self._avg(total)}
                for tool, total in sorted(self.totals.items())
            },
            "avg_total_calls_per_instance": self._avg(sum(self.totals.values())),
        }


class ToolUsageReport:
    def __init__(self, run_dir: Path):
        self._run_dir = run_dir
        self._usage: dict[str, VariantUsage] = {v: VariantUsage() for v in VARIANTS}

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
                    self._usage[variant].absorb(data[variant])

    def print_summary(self) -> None:
        print(f"=== {self._run_dir.name} ===")
        for variant, usage in self._usage.items():
            print()
            print(usage.render(variant))

    def write_json(self, out_path: Path) -> None:
        summary = {variant: usage.to_dict() for variant, usage in self._usage.items()}
        out_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        print(f"\nWrote {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize tool usage from comparison_report.json files")
    parser.add_argument("run_dir", help="Path to benchmark run directory (containing artifacts/)")
    parser.add_argument("--json", dest="json_out", help="Optionally dump the summary as JSON to this path")
    args = parser.parse_args()
    report = ToolUsageReport(Path(args.run_dir))
    report.process()
    report.print_summary()
    if args.json_out:
        report.write_json(Path(args.json_out))


if __name__ == "__main__":
    main()
