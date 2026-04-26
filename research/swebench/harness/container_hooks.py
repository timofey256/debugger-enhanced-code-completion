"""
Docker container creation with trace collection support.

This module provides functions to create Docker containers with trace collection
volumes and environment variables for SWE-bench evaluation.
"""

import docker
import logging
from pathlib import Path
from typing import Optional
import sys

from libs.env import require_env

sys.path.insert(0, require_env("SWE_BENCH_PATH"))
from swebench.harness.test_spec.test_spec import TestSpec
from swebench.harness.constants import DOCKER_USER


def create_traced_container(
    client: docker.DockerClient,
    test_spec: TestSpec,
    run_id: str,
    trace_output_dir: str,
    trace_collector_dir: str,
    logger: Optional[logging.Logger] = None,
) -> docker.models.containers.Container:
    """
    Create a Docker container with trace collection volumes and environment.

    This function replicates SWE-bench's build_container() logic but adds:
    - Volume mounts for trace collectors and output
    - Environment variables for trace collection activation

    Args:
        client: Docker client instance
        test_spec: SWE-bench TestSpec for the instance
        run_id: Run ID for container naming
        trace_output_dir: Host directory for trace output (per-instance)
        trace_collector_dir: Host directory containing trace collectors
        logger: Optional logger for debugging

    Returns:
        Created Docker container (not started)

    Raises:
        docker.errors.APIError: If container creation fails
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    instance_id = test_spec.instance_id
    logger.info(f"Creating traced container for {instance_id}...")

    # Ensure output directory exists with correct permissions
    # Convert to absolute path (Docker requires absolute paths for volumes)
    output_path = Path(trace_output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    output_path.chmod(0o777)  # Ensure container can write

    # Convert trace_collector_dir to absolute path as well
    collector_path = Path(trace_collector_dir).resolve()

    # Prepare volume mounts (use absolute paths)
    volumes = {
        str(collector_path): {
            "bind": "/opt/tracers",
            "mode": "ro"  # Read-only
        },
        str(output_path): {
            "bind": "/trace_output",
            "mode": "rw"  # Read-write
        }
    }

    # Prepare environment variables
    environment = {
        "PYTHONPATH": "/opt/tracers:/testbed",
        "AUTO_DEBUG_JSON": "/trace_output/auto_debug.json"
    }

    # Get docker run args from test spec (for cap_add, etc.)
    run_args = test_spec.docker_specs.get("run_args", {})
    cap_add = run_args.get("cap_add", [])

    logger.info(f"Volume mounts: {volumes}")
    logger.info(f"Environment: {environment}")

    try:
        # Create container with trace collection support
        # This mirrors docker_build.py:516-524 but adds volumes and environment
        container = client.containers.create(
            image=test_spec.instance_image_key,
            name=test_spec.get_instance_container_name(run_id),
            user=DOCKER_USER,
            detach=True,
            command="tail -f /dev/null",
            platform=test_spec.platform,
            cap_add=cap_add,
            volumes=volumes,
            environment=environment,
        )

        logger.info(f"Traced container created: {container.id}")
        return container

    except Exception as e:
        logger.error(f"Failed to create traced container for {instance_id}: {e}")
        raise


def verify_trace_setup(
    container: docker.models.containers.Container,
    logger: Optional[logging.Logger] = None
) -> bool:
    """
    Verify that trace collection is properly set up in the container.

    Checks:
    - /opt/tracers directory exists and contains tracers
    - /trace_output directory exists and is writable

    Note: Environment variables (PYTHONPATH, AUTO_DEBUG_JSON) are set in the eval
    script itself, so we don't check them at the container level.

    Args:
        container: Docker container to verify
        logger: Optional logger for output

    Returns:
        True if all checks pass, False otherwise
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    checks_passed = True

    # Check /opt/tracers exists and contains trace collectors
    result = container.exec_run("ls -la /opt/tracers")
    if result.exit_code != 0:
        logger.error("/opt/tracers directory not found in container")
        checks_passed = False
    else:
        logger.info("/opt/tracers directory found")
        # Verify trace collectors exist
        result = container.exec_run("ls /opt/tracers/*.py")
        if result.exit_code == 0:
            logger.info(f"Trace collectors available: {result.output.decode().strip()}")
        else:
            logger.warning("No Python trace collectors found in /opt/tracers")

    # Check /trace_output exists and is writable
    result = container.exec_run("touch /trace_output/test_write")
    if result.exit_code != 0:
        logger.error("/trace_output directory not writable")
        checks_passed = False
    else:
        logger.info("/trace_output directory is writable")
        container.exec_run("rm /trace_output/test_write")

    # Note: Environment variables are set in the eval script, not at container level
    logger.info("Environment variables will be set in eval script (PYTHONPATH, AUTO_DEBUG_JSON)")

    return checks_passed
