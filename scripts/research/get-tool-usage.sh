#!/bin/bash
# Summarize tool usage from comparison_report.json files of a benchmark run.
#
# Usage: get-tool-usage.sh RUN_DIR [--json OUT.json]
#
# TODO: rewrite this mess as python script!
set -uo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $(basename "$0") RUN_DIR [--json OUT.json]" >&2
  exit 2
fi

RUN_DIR="$1"
shift
JSON_OUT=""
if [[ "${1:-}" == "--json" ]]; then
  JSON_OUT="${2:-}"
fi

RUN_DIR="$RUN_DIR" JSON_OUT="$JSON_OUT" python3 - <<'PY'
import json
import os
import glob
from collections import defaultdict

run_dir = os.environ["RUN_DIR"]
json_out = os.environ.get("JSON_OUT") or ""

VARIANTS = ("without_runtime", "with_runtime")

artifacts_dir = os.path.join(run_dir, "artifacts")
if not os.path.isdir(artifacts_dir):
    raise SystemExit(f"artifacts/ not found in {run_dir}")

reports = sorted(glob.glob(os.path.join(artifacts_dir, "*", "comparison_report.json")))
if not reports:
    raise SystemExit(f"No comparison_report.json files found in {artifacts_dir}")

totals = {v: defaultdict(int) for v in VARIANTS}
counts = {v: 0 for v in VARIANTS}

for path in reports:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for variant in VARIANTS:
        tc = data.get(variant, {}).get("tool_call_counts")
        if tc is None:
            continue
        counts[variant] += 1
        for tool, n in tc.items():
            totals[variant][tool] += int(n)

summary = {}
print(f"=== {os.path.basename(os.path.normpath(run_dir))} ===")
for variant in VARIANTS:
    n_inst = counts[variant]
    per_tool = {}
    print()
    print(f"-- {variant} (instances: {n_inst}) --")
    for tool in sorted(totals[variant]):
        total = totals[variant][tool]
        avg = total / n_inst if n_inst else 0.0
        per_tool[tool] = {"total": total, "avg_per_instance": avg}
        print(f"  {tool:<20} total={total:<6} avg={avg:.3f}")
    grand = sum(totals[variant].values())
    avg_total = grand / n_inst if n_inst else 0.0
    print(f"  {'TOTAL':<20} total={grand:<6} avg={avg_total:.3f}")
    summary[variant] = {
        "instances": n_inst,
        "tools": per_tool,
        "avg_total_calls_per_instance": avg_total,
    }

if json_out:
    with open(json_out, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
    print(f"\nWrote {json_out}")
PY
