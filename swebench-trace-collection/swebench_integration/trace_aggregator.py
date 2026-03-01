"""
Aggregate traces from multiple instances into unified dataset.
"""

import json
from pathlib import Path
from typing import Dict, Any, List


class TraceAggregator:
    """
    Aggregate auto_debug.json files into unified JSONL dataset.

    Output format (one JSON object per line):
    {
      "instance_id": "django__django-12345",
      "repo": "django/django",
      "framework": "pytest",
      "base_commit": "abc123",
      "test_failures": [...],
      "metadata": {...}
    }
    """

    def __init__(self, traces_dir: str):
        self.traces_dir = Path(traces_dir)

    def create_unified_dataset(
        self,
        output_file: str = "swebench_traces.jsonl",
        include_metadata: bool = True
    ):
        """
        Aggregate all traces into single JSONL file.

        Args:
            output_file: Output filename (relative to traces_dir)
            include_metadata: Include SWE-bench metadata
        """
        output_path = self.traces_dir / output_file

        with output_path.open('w') as f:
            for instance_dir in self.traces_dir.iterdir():
                if not instance_dir.is_dir():
                    continue

                trace_file = instance_dir / "auto_debug.json"
                if not trace_file.exists():
                    continue

                try:
                    # Load trace data
                    trace_data = json.loads(trace_file.read_text())

                    # Load metadata if available
                    metadata = {}
                    if include_metadata:
                        metadata = self._load_instance_metadata(instance_dir.name)

                    # Create unified entry
                    unified_entry = {
                        "instance_id": instance_dir.name,
                        "framework": metadata.get("framework", "unknown"),
                        "test_failures": trace_data,
                        "metadata": metadata
                    }

                    # Write as JSONL (one JSON per line)
                    f.write(json.dumps(unified_entry) + '\n')

                except Exception as e:
                    print(f"Error processing {instance_dir.name}: {e}")

        print(f"Created unified dataset at {output_path}")

    def _load_instance_metadata(self, instance_id: str) -> Dict[str, Any]:
        """
        Load SWE-bench metadata for instance.

        Args:
            instance_id: Instance ID

        Returns:
            Metadata dictionary
        """
        # TODO: Load from SWE-bench dataset
        # For now, return minimal metadata
        return {
            "instance_id": instance_id,
            "framework": "unknown"
        }

    def generate_statistics(self) -> Dict[str, Any]:
        """
        Generate statistics about collected traces.

        Returns:
            Statistics dictionary
        """
        stats = {
            "total_instances": 0,
            "successful": 0,
            "failed": 0,
            "by_framework": {},
            "total_failures": 0
        }

        for instance_dir in self.traces_dir.iterdir():
            if not instance_dir.is_dir():
                continue

            stats["total_instances"] += 1

            trace_file = instance_dir / "auto_debug.json"
            if trace_file.exists():
                stats["successful"] += 1

                try:
                    trace_data = json.loads(trace_file.read_text())
                    num_failures = len(trace_data) if isinstance(trace_data, list) else 1
                    stats["total_failures"] += num_failures
                except Exception:
                    pass
            else:
                stats["failed"] += 1

        return stats
