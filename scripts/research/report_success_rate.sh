#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 <run_directory>"
    echo ""
    echo "Read comparison_report.json files from a benchmark run and report"
    echo "success rates for without_runtime and with_runtime configurations."
    echo ""
    echo "Arguments:"
    echo "  run_directory  Path to a benchmark run directory containing artifacts/"
    exit 1
}

if [[ $# -ne 1 ]]; then
    usage
fi

RUN_DIR="$1"
ARTIFACTS_DIR="${RUN_DIR}/artifacts"

if [[ ! -d "${ARTIFACTS_DIR}" ]]; then
    echo "Error: artifacts directory not found at ${ARTIFACTS_DIR}" >&2
    exit 1
fi

reports=("${ARTIFACTS_DIR}"/*/comparison_report.json)

if [[ ${#reports[@]} -eq 0 || ! -f "${reports[0]}" ]]; then
    echo "Error: no comparison_report.json files found in ${ARTIFACTS_DIR}" >&2
    exit 1
fi

without_total=0  without_passed=0  without_failed=0  without_other=0
with_total=0     with_passed=0     with_failed=0     with_other=0

declare -A without_status_counts
declare -A with_status_counts

for report in "${reports[@]}"; do
    instance_id="$(basename "$(dirname "$report")")"

    without_status="$(python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
v = d.get('without_runtime', {})
print(v.get('outcome', {}).get('status', 'missing'))
" "$report")"

    with_status="$(python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
v = d.get('with_runtime', {})
print(v.get('outcome', {}).get('status', 'missing'))
" "$report")"

    without_total=$((without_total + 1))
    without_status_counts["$without_status"]=$(( ${without_status_counts["$without_status"]:-0} + 1 ))
    if [[ "$without_status" == "passed" ]]; then
        without_passed=$((without_passed + 1))
    fi

    with_total=$((with_total + 1))
    with_status_counts["$with_status"]=$(( ${with_status_counts["$with_status"]:-0} + 1 ))
    if [[ "$with_status" == "passed" ]]; then
        with_passed=$((with_passed + 1))
    fi
done

pct() {
    local num=$1 den=$2
    if [[ $den -eq 0 ]]; then
        echo "0.00"
    else
        python3 -c "print(f'{100*${num}/${den}:.2f}')"
    fi
}

echo "=== Benchmark Run: $(basename "$RUN_DIR") ==="
echo "Total instances evaluated: ${without_total}"
echo ""

echo "── without_runtime ──"
echo "  Passed: ${without_passed}/${without_total} ($(pct $without_passed $without_total)%)"
echo "  Status breakdown:"
for status in $(echo "${!without_status_counts[@]}" | tr ' ' '\n' | sort); do
    echo "    ${status}: ${without_status_counts[$status]}"
done
echo ""

echo "── with_runtime ──"
echo "  Passed: ${with_passed}/${with_total} ($(pct $with_passed $with_total)%)"
echo "  Status breakdown:"
for status in $(echo "${!with_status_counts[@]}" | tr ' ' '\n' | sort); do
    echo "    ${status}: ${with_status_counts[$status]}"
done
