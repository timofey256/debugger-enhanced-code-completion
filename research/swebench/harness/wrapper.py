"""
Wrapper for SWE-bench's run_instance with trace collection.

This module orchestrates trace collection by wrapping SWE-bench's
evaluation logic and adding trace collection setup.
"""

import json
import logging
import sys
import traceback
from pathlib import Path, PurePosixPath
from typing import Optional

import docker

from libs.env import require_env

sys.path.insert(0, require_env("SWE_BENCH_PATH"))

from swebench.harness.test_spec.test_spec import TestSpec
from swebench.harness.constants import (
    APPLY_PATCH_FAIL,
    APPLY_PATCH_PASS,
    DOCKER_PATCH,
    DOCKER_USER,
    DOCKER_WORKDIR,
    KEY_INSTANCE_ID,
    KEY_MODEL,
    KEY_PREDICTION,
    UTF8,
)
from swebench.harness.docker_utils import (
    cleanup_container,
    copy_to_container,
    exec_run_with_timeout,
)
from swebench.harness.docker_build import build_instance_image

# Git apply commands to try in order
GIT_APPLY_CMDS = [
    "git apply --verbose",
    "git apply --verbose --reject",
    "patch --batch --fuzz=5 -p1 -i",
]

# Local imports
from .container_hooks import create_traced_container, verify_trace_setup
from .eval_script_injector import inject_trace_setup, get_detected_framework


class TraceCollectionError(Exception):
    """Raised when trace collection fails."""
    pass


def run_instance_with_traces(
    test_spec: TestSpec,
    pred: dict,
    client: docker.DockerClient,
    run_id: str,
    trace_output_base: str,
    trace_collector_dir: str,
    timeout: Optional[int] = None,
    force_rebuild: bool = False,
    nocache: bool = False,
    skip_patch: bool = False,
    logger: Optional[logging.Logger] = None,
) -> dict:
    """
    Run a single SWE-bench instance with trace collection.

    This function wraps SWE-bench's run_instance logic and adds:
    - Trace collection setup (conftest.py injection for pytest)
    - Traced container creation (with volumes and environment)
    - Trace output validation

    Args:
        test_spec: SWE-bench TestSpec for the instance
        pred: Prediction dict with instance_id, model_name_or_path, model_patch
        client: Docker client instance
        run_id: Run ID for this evaluation
        trace_output_base: Base directory for trace outputs
        trace_collector_dir: Directory containing trace collectors
        timeout: Timeout for test execution (seconds)
        force_rebuild: Force rebuild of instance image
        nocache: Don't use cache when building images
        skip_patch: Skip patch application (useful for collecting traces from original failures)
        logger: Optional logger

    Returns:
        dict with keys:
            - success: bool - whether trace collection succeeded
            - instance_id: str - instance identifier
            - framework: str - detected framework
            - trace_path: str - path to trace output file
            - error: str - error message if failed

    Raises:
        TraceCollectionError: If trace collection fails
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    instance_id = test_spec.instance_id
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing: {instance_id}")
    logger.info(f"{'='*60}")

    # Detect framework
    framework = get_detected_framework(test_spec)
    logger.info(f"Detected framework: {framework}")

    # Inject trace setup into eval script
    logger.info("Injecting trace collection setup...")
    modified_test_spec = inject_trace_setup(test_spec)

    # Set up instance-specific trace output directory
    instance_trace_dir = Path(trace_output_base) / instance_id
    instance_trace_dir.mkdir(parents=True, exist_ok=True)
    instance_trace_dir.chmod(0o777)

    trace_output_file = instance_trace_dir / "auto_debug.json"
    logger.info(f"Trace output will be saved to: {trace_output_file}")

    container = None
    try:
        # Build instance image if needed
        if force_rebuild or not test_spec.is_remote_image:
            logger.info(f"Building instance image: {test_spec.instance_image_key}")
            build_instance_image(modified_test_spec, client, logger, nocache)

        # Create container with trace collection support
        logger.info("Creating traced container...")
        container = create_traced_container(
            client=client,
            test_spec=modified_test_spec,
            run_id=run_id,
            trace_output_dir=str(instance_trace_dir),
            trace_collector_dir=trace_collector_dir,
            logger=logger,
        )

        # Start the container
        container.start()
        logger.info(f"Container started: {container.id}")

        # Verify trace setup
        logger.info("Verifying trace collection setup...")
        if not verify_trace_setup(container, logger):
            raise TraceCollectionError("Trace setup verification failed")

        # Copy and apply patch (unless skip_patch is set)
        if skip_patch:
            logger.info("Skipping patch application (--skip-patch flag set)")
            logger.info("Will collect traces from original failing tests")
        else:
            # Copy model prediction as patch file to container
            logger.info("Copying patch to container...")
            patch_content = pred.get(KEY_PREDICTION, "")
            if not patch_content:
                logger.warning("Empty patch content")

            # Write patch to temp file
            temp_patch_file = instance_trace_dir / "patch.diff"
            temp_patch_file.write_text(patch_content)
            copy_to_container(container, temp_patch_file, PurePosixPath(DOCKER_PATCH))

            # Attempt to apply patch to container
            logger.info("Applying patch...")
            applied_patch = False
            for git_apply_cmd in GIT_APPLY_CMDS:
                result = container.exec_run(
                    f"{git_apply_cmd} {DOCKER_PATCH}",
                    workdir=DOCKER_WORKDIR,
                    user=DOCKER_USER,
                )
                if result.exit_code == 0:
                    logger.info(f"{APPLY_PATCH_PASS}: {git_apply_cmd}")
                    applied_patch = True
                    break
                else:
                    logger.debug(f"Failed to apply patch with {git_apply_cmd}")

            if not applied_patch:
                raise TraceCollectionError(
                    f"{APPLY_PATCH_FAIL}: All git apply strategies failed"
                )

        # Copy eval script to container
        logger.info("Copying eval script to container...")
        temp_eval_file = instance_trace_dir / "eval.sh"
        temp_eval_file.write_text(modified_test_spec.eval_script)
        copy_to_container(container, temp_eval_file, PurePosixPath("/eval.sh"))

        # Run eval script
        logger.info("Running tests with trace collection...")
        test_output, timed_out, runtime = exec_run_with_timeout(
            container, "/bin/bash /eval.sh", timeout
        )

        logger.info(f"Test runtime: {runtime:.2f} seconds")

        # Save test output for debugging
        test_output_file = instance_trace_dir / "test_output.txt"
        test_output_file.write_text(test_output)
        logger.info(f"Test output saved to: {test_output_file}")

        if timed_out:
            raise TraceCollectionError(f"Test execution timed out after {timeout}s")

        # Check if trace file was created
        if not trace_output_file.exists():
            raise TraceCollectionError(
                f"Trace file not created: {trace_output_file}. "
                f"Tests may not have failed, or trace collection did not activate."
            )

        # Validate trace file
        try:
            with open(trace_output_file, 'r') as f:
                traces = json.load(f)

            if not isinstance(traces, list):
                raise TraceCollectionError(
                    f"Invalid trace format: expected list, got {type(traces)}"
                )

            if len(traces) == 0:
                logger.warning("Trace file is empty (no test failures captured)")
            else:
                logger.info(f"Successfully collected {len(traces)} test failure traces")

        except json.JSONDecodeError as e:
            raise TraceCollectionError(f"Invalid JSON in trace file: {e}")

        # Success!
        logger.info(f"✓ {instance_id}: Trace collected successfully")
        logger.info(f"  Framework: {framework}")
        logger.info(f"  Trace file: {trace_output_file}")
        logger.info(f"  Failures captured: {len(traces)}")

        return {
            "success": True,
            "instance_id": instance_id,
            "framework": framework,
            "trace_path": str(trace_output_file),
            "num_failures": len(traces),
            "runtime": runtime,
        }

    except Exception as e:
        error_msg = f"Failed to collect traces for {instance_id}: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)

        return {
            "success": False,
            "instance_id": instance_id,
            "framework": framework,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }

    finally:
        # Always cleanup container
        if container is not None:
            logger.info(f"Cleaning up container for {instance_id}...")
            cleanup_container(client, container, logger)
