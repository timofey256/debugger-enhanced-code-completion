This folder contains small helper scripts for reporting results of benchmark runs.
All of them take a benchmark run directory (the one containing `artifacts/`) as the argument.

#### Description of content

- `research/report_metrics.py` :
prints the main benchmark statistics per variant: number of resolved instances and apply rate.
Useful to re-grade any finished run without re-running it.
Fast.

- `research/report_localization.py` :
prints size-aware localization metrics per variant: precision/recall/F1 on file, function and line level, computed by comparing the generated patch against the reference patch.
Slower.

- `research/report_tool_usage.py` :
summarizes how many times each tool was called in the run, from the `comparison_report.json` files.
Optionally dumps the summary as JSON with `--json OUT.json`.
