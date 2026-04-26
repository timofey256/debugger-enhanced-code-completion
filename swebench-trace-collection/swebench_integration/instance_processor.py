"""
Process individual SWE-bench instances with trace collection.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional


@dataclass
class ProcessResult:
    """Result of processing a single instance."""
    instance_id: str
    success: bool
    framework: str
    trace_path: Optional[str] = None
    error: Optional[str] = None
    num_failures: int = 0


def process_instance(
    instance: Dict[str, Any],
    framework: str,
    output_dir: str
) -> ProcessResult:
    """
    Process single SWE-bench instance with trace collection.

    Args:
        instance: SWE-bench instance dictionary
        framework: Detected framework (pytest, unittest, django)
        output_dir: Base output directory

    Returns:
        ProcessResult with success status and trace location
    """
    instance_id = instance['instance_id']
    trace_output = Path(output_dir) / instance_id

    try:
        # TODO: Implement actual test execution
        # This will:
        # 1. Create TestSpec with trace hooks
        # 2. Run test in Docker container
        # 3. Check for trace output

        trace_file = trace_output / "auto_debug.json"

        if trace_file.exists():
            # Count failures in trace
            import json
            trace_data = json.loads(trace_file.read_text())
            num_failures = len(trace_data) if isinstance(trace_data, list) else 1

            return ProcessResult(
                instance_id=instance_id,
                success=True,
                framework=framework,
                trace_path=str(trace_file),
                num_failures=num_failures
            )
        else:
            return ProcessResult(
                instance_id=instance_id,
                success=False,
                framework=framework,
                error="No trace file generated"
            )

    except Exception as e:
        return ProcessResult(
            instance_id=instance_id,
            success=False,
            framework=framework,
            error=str(e)
        )
