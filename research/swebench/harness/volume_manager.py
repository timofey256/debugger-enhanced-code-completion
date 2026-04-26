"""
Docker volume management for trace collection.

Manages host directories and Docker volume mounts for collecting
trace output from SWE-bench containers.
"""

import os
from pathlib import Path
from typing import List, Tuple


class TraceOutputManager:
    """
    Manage Docker volume mounts for trace collection output.

    Creates host directories and generates Docker mount arguments
    to collect auto_debug.json files from containers.
    """

    def __init__(self, base_dir: str = "./swebench_traces"):
        self.base_dir = Path(base_dir).absolute()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_output_volume(self, instance_id: str) -> Path:
        """
        Create host directory for instance trace output.

        Args:
            instance_id: SWE-bench instance ID

        Returns:
            Absolute path to output directory
        """
        output_path = self.base_dir / instance_id
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path

    def get_docker_mount_args(self, instance_id: str) -> List[str]:
        """
        Get Docker volume mount arguments for instance.

        Args:
            instance_id: SWE-bench instance ID

        Returns:
            List of Docker arguments: ["-v", "host:container:rw"]
        """
        host_path = self.create_output_volume(instance_id)
        return ["-v", f"{host_path}:/trace_output:rw"]

    def get_trace_file_path(self, instance_id: str) -> Path:
        """
        Get path to auto_debug.json for instance.

        Args:
            instance_id: SWE-bench instance ID

        Returns:
            Path to trace JSON file
        """
        return self.base_dir / instance_id / "auto_debug.json"

    def trace_exists(self, instance_id: str) -> bool:
        """
        Check if trace file exists for instance.

        Args:
            instance_id: SWE-bench instance ID

        Returns:
            True if trace file exists
        """
        return self.get_trace_file_path(instance_id).exists()

    def get_tracer_mount_args(self, tracers_dir: str) -> Tuple[List[str], List[str]]:
        """
        Get Docker mount and environment args for trace collectors.

        Args:
            tracers_dir: Path to libs/tracing directory

        Returns:
            Tuple of (mount_args, env_args)
        """
        tracers_path = Path(tracers_dir).absolute()

        mount_args = ["-v", f"{tracers_path}:/opt/tracers:ro"]

        env_args = [
            "-e", "PYTHONPATH=/opt/tracers:$PYTHONPATH",
            "-e", "AUTO_DEBUG_JSON=/trace_output/auto_debug.json"
        ]

        return mount_args, env_args

    def cleanup_instance(self, instance_id: str):
        """
        Remove trace output directory for instance.

        Args:
            instance_id: SWE-bench instance ID
        """
        output_dir = self.base_dir / instance_id

        if output_dir.exists():
            import shutil
            shutil.rmtree(output_dir)

    def get_all_instances(self) -> List[str]:
        """
        Get list of all instance IDs with trace data.

        Returns:
            List of instance IDs
        """
        instances = []

        for item in self.base_dir.iterdir():
            if item.is_dir():
                instances.append(item.name)

        return instances
