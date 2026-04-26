"""
Minimal hooks for SWE-bench TestSpec to enable trace collection.

This provides the interface for injecting trace collectors into
SWE-bench's Docker container execution.
"""

from typing import List, Optional


def get_trace_collection_args(
    trace_collector_dir: str,
    trace_output_dir: str
) -> List[str]:
    """
    Generate Docker arguments for trace collection.

    Args:
        trace_collector_dir: Path to libs/tracing module
        trace_output_dir: Path for output (host directory)

    Returns:
        List of Docker arguments to append
    """
    args = []

    # Mount trace collectors (read-only)
    args.extend(["-v", f"{trace_collector_dir}:/opt/tracers:ro"])

    # Mount output directory (read-write)
    args.extend(["-v", f"{trace_output_dir}:/trace_output:rw"])

    # Set PYTHONPATH for auto-activation
    args.extend(["-e", "PYTHONPATH=/opt/tracers:$PYTHONPATH"])

    # Set output path
    args.extend(["-e", "AUTO_DEBUG_JSON=/trace_output/auto_debug.json"])

    return args


def patch_testspec(testspec, trace_collector_dir: str, trace_output_dir: str):
    """
    Patch TestSpec instance to include trace collection.

    Args:
        testspec: SWE-bench TestSpec object
        trace_collector_dir: Path to trace collectors
        trace_output_dir: Path for trace output

    Returns:
        Modified testspec
    """
    # TODO: Implement actual patching
    # This will modify testspec.get_instance_container_args()
    # to include trace collection arguments

    return testspec


# Minimal modification to add to SWE-bench's test_spec.py:
"""
def get_instance_container_args(
    self,
    trace_collector_dir: str = None,
    trace_output_dir: str = None
):
    args = [...existing args...]

    # Add trace collection if enabled
    if trace_collector_dir and trace_output_dir:
        from research.swebench.harness.testspec_hooks import get_trace_collection_args
        args.extend(get_trace_collection_args(trace_collector_dir, trace_output_dir))

    return args
"""
