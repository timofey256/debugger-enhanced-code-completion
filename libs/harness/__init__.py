from __future__ import annotations

import sys

from libs.env import require_env

try:
    import swebench  # noqa: F401
except ModuleNotFoundError:
    sys.path.insert(0, require_env("SWE_BENCH_PATH"))
    import swebench  # noqa: F401

from libs.harness.filters import PathFilter, StdlibFilter
from libs.harness.framework_detector import Framework, FrameworkDetector
from libs.harness.trace_output import TraceOutputManager
from libs.harness.traced_runner import (
    RunResult,
    TraceCollectionError,
    TracedInstanceRunner,
)
from libs.harness.instance_comparison import (
    ComparisonConfig,
    ComparisonReport,
    InstanceComparison,
    Outcome,
    Status,
    Variant,
    VariantResult,
    Verdict,
)

__all__ = [
    "PathFilter",
    "StdlibFilter",
    "Framework",
    "FrameworkDetector",
    "TraceOutputManager",
    "RunResult",
    "TraceCollectionError",
    "TracedInstanceRunner",
    "ComparisonConfig",
    "ComparisonReport",
    "InstanceComparison",
    "Outcome",
    "Status",
    "Variant",
    "VariantResult",
    "Verdict",
]
